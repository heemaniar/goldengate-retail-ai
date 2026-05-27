"""
prep_data.py — Augment the Istanbul Mall dataset for MallPulse.

Run from the mallpulse/ project root with the venv active:
    python prep_data.py

Requires: customer_shopping_data.csv in the same directory.
Produces: 8 CSVs in ./data/

Section 9 — fact_foot_traffic design notes
-------------------------------------------
Visitor counts are grounded in the actual daily transaction volumes from the
source CSV, not purely random, so the agent's answers about foot traffic are
consistent with its answers about revenue and transactions.

Key design decisions:
  1. GLA baseline  : daily visitor target = gross_leasable_sqm × 0.08
                     (calibrated to typical Istanbul mall benchmarks)
  2. Busyness mult : actual daily txn_count ÷ 28-day centred rolling average
                     per mall — a day with twice the usual transactions gets
                     twice the foot traffic. Clipped to [0.30, 3.0].
  3. 2020 backfill : source CSV starts Jan 2021; the 2020 period uses each
                     mall's long-run average txn rate (busy_mult = 1.0) so
                     the calendar spine is complete without gaps.
  4. Browsing boost: weekends +40%, Turkish holidays ×1.50 on top — captures
                     visitors who come to browse but do not purchase (real
                     conversion rates are lower on leisure days).
  5. Hourly spread : Gaussian bell curve centred at 14:00 (σ = 3 h) then
                     Poisson noise, giving realistic intra-day variance.
"""

import os
import hashlib
import numpy as np
import pandas as pd
import requests
import holidays
from pathlib import Path

def dhash(*args) -> int:
    """Deterministic hash regardless of PYTHONHASHSEED.
    Uses MD5 so output is identical across machines and Python versions."""
    key = '|'.join(str(a) for a in args)
    return int(hashlib.md5(key.encode()).hexdigest(), 16)

np.random.seed(42)
DATA = Path('data')
DATA.mkdir(exist_ok=True)

# ── 1) Load raw Istanbul data ────────────────────────────────────────────────
print("Loading customer_shopping_data.csv...")
raw = pd.read_csv('customer_shopping_data.csv')
raw['invoice_date'] = pd.to_datetime(raw['invoice_date'], dayfirst=True)
print(f"  {len(raw):,} rows | date range: {raw['invoice_date'].min().date()} → {raw['invoice_date'].max().date()}")

# ── 2) dim_mall — 10 real Istanbul malls with lat/lon ────────────────────────
MALL_GEO = {
    'Kanyon':             (41.0865, 29.0136, 250000, 2006),
    'Forum Istanbul':     (41.0408, 28.8950, 495000, 2009),
    'Metrocity':          (41.0866, 29.0090,  65000, 2003),
    'Metropol AVM':       (40.9866, 29.1144,  75000, 2005),
    'Istinye Park':       (41.1132, 29.0287,  79000, 2007),
    'Mall of Istanbul':   (41.0796, 28.7967, 350000, 2014),
    'Emaar Square Mall':  (40.9991, 29.0364, 150000, 2017),
    'Cevahir AVM':        (41.0617, 28.9885, 420000, 2005),
    'Viaport Outlet':     (40.9105, 29.3168, 100000, 2009),
    'Zorlu Center':       (41.0680, 29.0166, 105000, 2013),
}

dim_mall = pd.DataFrame([
    {
        'mall_id': f'm{i+1:02d}',
        'mall_name': name,
        'city': 'Istanbul',
        'country': 'Turkey',
        'latitude': lat,
        'longitude': lon,
        'gross_leasable_sqm': sqm,
        'opened_year': yr,
    }
    for i, (name, (lat, lon, sqm, yr)) in enumerate(MALL_GEO.items())
])
dim_mall.to_csv(DATA / 'dim_mall.csv', index=False)
print(f"  dim_mall.csv: {len(dim_mall)} rows")

# ── 3) dim_tenant — one tenant per (mall, category) combo ───────────────────
TENANTS = {
    'Clothing':        ['Zara', 'H&M', 'LC Waikiki', 'Mango', 'Bershka'],
    'Shoes':           ['Nike', 'Flo', 'Derimod', 'Skechers'],
    'Books':           ['D&R', 'Remzi'],
    'Cosmetics':       ['Sephora', 'MAC', 'Watsons', 'Gratis'],
    'Food & Beverage': ['Starbucks', 'Mado', 'Burger King'],
    'Toys':            ['Toyzz Shop', 'Lego Store'],
    'Technology':      ['MediaMarkt', 'Vatan Bilgisayar'],
    'Souvenir':        ['Istanbul Memories'],
}

# Store format — reflects what each brand actually is in a real Istanbul mall.
# Anchor: large format driving overall traffic; Restaurant Pad: full-service F&B;
# Food Court: counter-only shared-hall unit; Kiosk: no-wall corridor stand.
TENANT_FORMAT = {
    'Zara':              'Anchor',          # flagship, 2+ floors, bookends wing
    'H&M':               'Anchor',
    'LC Waikiki':        'Anchor',
    'MediaMarkt':        'Anchor',          # consumer electronics hypermarket
    'Vatan Bilgisayar':  'Anchor',          # computing superstore
    'Mango':             'In-line',
    'Bershka':           'In-line',
    'Nike':              'In-line',
    'Flo':               'In-line',
    'Derimod':           'In-line',
    'Skechers':          'In-line',
    'D&R':               'In-line',
    'Remzi':             'In-line',
    'Sephora':           'In-line',
    'MAC':               'In-line',
    'Watsons':           'In-line',
    'Gratis':            'In-line',
    'Toyzz Shop':        'In-line',
    'Lego Store':        'In-line',
    'Starbucks':         'Restaurant Pad',  # full-service café, sometimes terrace
    'Mado':              'Restaurant Pad',  # full-service Turkish dessert/dining
    'Burger King':       'Food Court',      # counter-service, shared seating hall
    'Istanbul Memories': 'Kiosk',           # open-fronted souvenir stand, no walls
}

# Subcategory — specific retail segment within the parent category.
# Enables queries like "which Fast Fashion subcategory drives most revenue?"
TENANT_SUBCATEGORY = {
    'Zara':              'Fast Fashion',
    'H&M':               'Fast Fashion',
    'LC Waikiki':        'Fast Fashion',
    'Mango':             'Premium Casual',
    'Bershka':           'Fast Fashion',
    'Nike':              'Athletic',
    'Flo':               'Casual',
    'Derimod':           'Leather Goods',
    'Skechers':          'Athletic',
    'D&R':               'Books & Music',
    'Remzi':             'Books & Music',
    'Sephora':           'Makeup & Skincare',
    'MAC':               'Makeup',
    'Watsons':           'Pharmacy & Health',
    'Gratis':            'Pharmacy & Health',
    'Starbucks':         'Coffee & Café',
    'Mado':              'Casual Dining',
    'Burger King':       'Fast Food',
    'Toyzz Shop':        'Licensed Toys',
    'Lego Store':        'Educational Toys',
    'MediaMarkt':        'Consumer Electronics',
    'Vatan Bilgisayar':  'Computing',
    'Istanbul Memories': 'Local Gifts',
}

# Base unit size (sqm) grounded in real Istanbul mall footprints.
# Anchors (Zara ~1200, MediaMarkt ~2800) are order-of-magnitude larger than
# kiosks (Istanbul Memories ~18) — correcting the previous flat 100–500 range.
TENANT_SIZE_BASE = {
    'Zara':              1200,
    'H&M':               1000,
    'LC Waikiki':        1500,
    'MediaMarkt':        2800,
    'Vatan Bilgisayar':  1400,
    'Mango':              350,
    'Bershka':            280,
    'Nike':               180,
    'Flo':                140,
    'Derimod':            155,
    'Skechers':           130,
    'Sephora':            160,
    'MAC':                 90,
    'Watsons':            190,
    'Gratis':             170,
    'D&R':                420,
    'Remzi':              310,
    'Toyzz Shop':         380,
    'Lego Store':         220,
    'Starbucks':          140,
    'Mado':               270,
    'Burger King':         95,
    'Istanbul Memories':   18,
}

# Mall size multiplier — larger GLA malls can accommodate larger individual units.
MALL_SIZE_MULT = {
    'Forum Istanbul':    1.30,
    'Cevahir AVM':       1.25,
    'Mall of Istanbul':  1.20,
    'Kanyon':            1.10,
    'Emaar Square Mall': 1.00,
    'Zorlu Center':      0.95,
    'Viaport Outlet':    0.90,
    'Istinye Park':      0.90,
    'Metropol AVM':      0.85,
    'Metrocity':         0.85,
}

mall_lookup = dict(zip(dim_mall['mall_name'], dim_mall['mall_id']))
tenants = []
for mall in dim_mall['mall_name']:
    for cat, names in TENANTS.items():
        chosen    = names[dhash(mall, cat) % len(names)]
        base_sqm  = TENANT_SIZE_BASE[chosen]
        mall_mult = MALL_SIZE_MULT[mall]
        # ±12% deterministic variation around the brand baseline
        variation = 0.88 + (dhash(mall, chosen, 'size') % 25) / 100  # 0.88–1.12
        unit_size = max(8, int(base_sqm * mall_mult * variation))
        tenants.append({
            'tenant_id': (
                f't_{chosen.lower().replace(" ", "_").replace("&", "").replace("__", "_")}'
                f'_{mall_lookup[mall]}'
            ),
            'tenant_name':   chosen,
            'mall_id':       mall_lookup[mall],
            'category':      cat,
            'subcategory':   TENANT_SUBCATEGORY[chosen],
            'unit_size_sqm': unit_size,
            'store_format':  TENANT_FORMAT[chosen],
        })

dim_tenant = pd.DataFrame(tenants)

# ── 3c) Tenant turnover — SCD Type 2 ─────────────────────────────────────────
# Real malls see tenant turnover every 3-7 years.  We model two turnover waves:
#   Cohort 0 (lease expired 2021-12-31): replacement moves in 2022-01-01
#   Cohort 1 (lease expired 2023-09-30): replacement moves in 2023-10-01
#
# Categories with only one brand option (Souvenir) cannot be replaced —
# those slots stay open-ended.  All other categories cycle to the next brand
# in the TENANTS pool (deterministic via dhash).
#
# effective_from / effective_to: half-open intervals [from, to] stored as dates.
# is_replacement flag: used in dim_lease to assign fresh 5-year leases.

_COHORT_TENURE = {
    0: (pd.Timestamp('2018-01-01'), pd.Timestamp('2021-12-31'), pd.Timestamp('2022-01-01')),
    1: (pd.Timestamp('2020-06-01'), pd.Timestamp('2023-09-30'), pd.Timestamp('2023-10-01')),
    2: (pd.Timestamp('2020-01-01'), pd.Timestamp('2026-07-06'), None),
    3: (pd.Timestamp('2021-01-01'), pd.Timestamp('2026-07-06'), None),
}
_SCD_END = pd.Timestamp('2026-07-06')
_mall_name_lu = dim_mall.set_index('mall_id')['mall_name']

orig_rows, repl_rows = [], []

for row in dim_tenant.to_dict('records'):
    tid       = row['tenant_id']
    cohort    = dhash(tid, 'cohort') % 4
    cat       = row['category']
    mall_id   = row['mall_id']
    mall_name = _mall_name_lu[mall_id]
    cat_names = TENANTS[cat]

    eff_from, eff_to, repl_start = _COHORT_TENURE[cohort]
    gets_replacement = (cohort in (0, 1)) and (len(cat_names) >= 2)

    if not gets_replacement:
        # No successor — keep slot open through the full sim horizon
        eff_to = _SCD_END

    row['effective_from'] = eff_from
    row['effective_to']   = eff_to
    row['is_replacement'] = False
    orig_rows.append(row)

    if gets_replacement:
        orig_idx  = dhash(mall_name, cat) % len(cat_names)
        repl_name = cat_names[(orig_idx + 1) % len(cat_names)]

        base_sqm  = TENANT_SIZE_BASE[repl_name]
        mall_mult = MALL_SIZE_MULT[mall_name]
        variation = 0.88 + (dhash(mall_name, repl_name, 'size') % 25) / 100
        unit_size = max(8, int(base_sqm * mall_mult * variation))

        # _r suffix avoids ID collision when the same brand is a primary tenant
        # elsewhere in the portfolio
        repl_tid = (
            f't_{repl_name.lower().replace(" ", "_").replace("&", "").replace("__", "_")}'
            f'_{mall_id}_r'
        )
        repl_rows.append({
            'tenant_id':      repl_tid,
            'tenant_name':    repl_name,
            'mall_id':        mall_id,
            'category':       cat,
            'subcategory':    TENANT_SUBCATEGORY[repl_name],
            'unit_size_sqm':  unit_size,
            'store_format':   TENANT_FORMAT[repl_name],
            'effective_from': repl_start,
            'effective_to':   _SCD_END,
            'is_replacement': True,
        })

dim_tenant = pd.DataFrame(orig_rows + repl_rows)
dim_tenant.to_csv(DATA / 'dim_tenant.csv', index=False)
print(f"  dim_tenant.csv: {len(dim_tenant)} rows "
      f"({len(orig_rows)} original + {len(repl_rows)} replacements)")

# ── 3b) Seasonal date resampling ─────────────────────────────────────────────
# The source CSV dates are uniformly distributed (synthetic origin) — every day
# of the week and every month appears with equal probability. That kills any
# seasonality signal, making ARIMA_PLUS produce a flat forecast.
#
# Fix: reassign invoice_date per mall using a probability distribution that
# reflects real Istanbul mall behaviour:
#   • Weekends (Sat/Sun) : +40% weight over weekdays (leisure browsing)
#   • Turkish public holidays: ×1.50 additional multiplier
#   • Monthly pattern: Dec +30% (gifts/NYE), Nov +15% (early winter),
#                      Jan +10% (post-holiday clearance), Jul/Aug −15% (heat)
#
# Only the date is redistributed; transaction amounts, customers, and tenant
# assignments are untouched. Random seed (42) is set globally → reproducible.
print("  Resampling invoice_date with seasonal weights...")
# Only resample the original 2021-2023 rows whose dates are synthetic/uniform.
# Rows added by simulate_data.py (dates >= 2023-03-09) already carry realistic
# seasonal dates and must NOT be resampled.
_SIM_CUTOFF  = pd.Timestamp('2023-03-09')
_orig_mask   = raw['invoice_date'] < _SIM_CUTOFF

_tr_hols    = set(holidays.TR(years=range(2021, 2027)).keys())
_date_spine = pd.date_range('2021-01-01', '2023-03-08', freq='D')

_MONTH_MULT = {
    1: 1.10,   # January  — clearance sales
    2: 0.90,   # February — quiet shoulder month
    3: 0.95,   # March
    4: 1.00,
    5: 1.00,
    6: 0.95,
    7: 0.85,   # July  — summer heat, Istanbulites leave the city
    8: 0.85,   # August
    9: 1.00,
    10: 1.05,  # October — back-to-school tail
    11: 1.15,  # November — early winter + Black Friday
    12: 1.30,  # December — gift season / New Year's Eve
}

def _date_wt(d: pd.Timestamp) -> float:
    w = _MONTH_MULT[d.month]
    if d.weekday() >= 5:      w *= 1.40   # Sat/Sun
    if d.date() in _tr_hols:  w *= 1.50   # Turkish public holiday
    return w

_wts = np.array([_date_wt(d) for d in _date_spine], dtype=float)
_wts /= _wts.sum()

for _mall in raw['shopping_mall'].unique():
    _idx     = raw[_orig_mask & (raw['shopping_mall'] == _mall)].index
    _sampled = np.random.choice(len(_date_spine), size=len(_idx), replace=True, p=_wts)
    raw.loc[_idx, 'invoice_date'] = _date_spine[_sampled]

# Verify the redistribution worked (check only original rows)
_orig_dates   = raw.loc[_orig_mask, 'invoice_date']
_dow_dist     = _orig_dates.dt.day_name().value_counts()
_weekend_share = (_dow_dist.get('Saturday', 0) + _dow_dist.get('Sunday', 0)) / len(_orig_dates)
print(f"    Weekend share after resampling (orig rows): {_weekend_share:.1%} (expected ~27–30%)")
del _tr_hols, _date_spine, _MONTH_MULT, _wts, _orig_mask, _SIM_CUTOFF

# ── 4) fact_transactions — date-aware tenant lookup ──────────────────────────
# With SCD Type 2 dim_tenant, the same (mall, category) slot may have multiple
# tenant rows with non-overlapping effective periods.  We fan-out the join
# (one interim row per tenant period at that slot) then keep only the row where
# the transaction date falls within the active tenant's window.
mall_name_to_id = dict(zip(dim_mall['mall_name'], dim_mall['mall_id']))
raw['mall_id'] = raw['shopping_mall'].map(mall_name_to_id)

_tenant_periods = dim_tenant[
    ['mall_id', 'category', 'tenant_id', 'effective_from', 'effective_to']
].copy()

# Fan-out: each transaction gets one candidate row per tenant period at its slot
_raw_merged = raw.merge(_tenant_periods, on=['mall_id', 'category'], how='left')

# Keep only the row where the transaction date is within the active period
_date_mask = (
    (_raw_merged['invoice_date'] >= _raw_merged['effective_from']) &
    (_raw_merged['invoice_date'] <= _raw_merged['effective_to'])
)
_raw_matched = _raw_merged[_date_mask].drop(
    columns=['effective_from', 'effective_to']
)

_gap_count = len(raw) - len(_raw_matched)
if _gap_count > 0:
    print(f"    Note: {_gap_count:,} transactions fell in a vacancy gap — dropped")

# NOTE: the source CSV 'price' column is the LINE TOTAL (quantity × unit_price),
# not the unit price. Computed on raw (for dim_customer in section 5) and on
# the matched subset (for fact_transactions).
raw['total_amount'] = raw['price'].round(2)
_raw_matched = _raw_matched.copy()
_raw_matched['total_amount'] = _raw_matched['price'].round(2)
_raw_matched['unit_price']   = (_raw_matched['price'] / _raw_matched['quantity']).round(2)

fact_transactions = _raw_matched.rename(columns={'invoice_date': 'date'})[[
    'invoice_no', 'tenant_id', 'mall_id', 'customer_id', 'date',
    'category', 'quantity', 'unit_price', 'total_amount', 'payment_method',
]]
fact_transactions.to_csv(DATA / 'fact_transactions.csv', index=False)
print(f"  fact_transactions.csv: {len(fact_transactions):,} rows")

# ── 5) dim_customer ──────────────────────────────────────────────────────────
def age_band(a):
    if a < 25: return '18-24'
    if a < 35: return '25-34'
    if a < 45: return '35-44'
    if a < 55: return '45-54'
    if a < 65: return '55-64'
    return '65+'

# Loyalty tier: spend-based segmentation on single transaction amount.
# The source dataset has no repeat-purchase history (each customer_id appears
# exactly once), so transaction value is used as a proxy for spend level.
# Percentile thresholds: Gold ≥ p85, Silver p60–p85, Bronze p30–p60, Standard < p30.
spend = raw.groupby('customer_id')['total_amount'].sum()
p85, p60, p30 = spend.quantile(0.85), spend.quantile(0.60), spend.quantile(0.30)
print(f"    Loyalty thresholds — Gold ≥ ₺{p85:.0f} | Silver ≥ ₺{p60:.0f} | Bronze ≥ ₺{p30:.0f}")

def loyalty_tier(amount):
    if amount >= p85: return 'Gold'
    if amount >= p60: return 'Silver'
    if amount >= p30: return 'Bronze'
    return 'Standard'

dim_customer = raw[['customer_id', 'gender', 'age']].drop_duplicates('customer_id').copy()
dim_customer['age_band']     = dim_customer['age'].apply(age_band)
dim_customer['loyalty_tier'] = dim_customer['customer_id'].map(spend).apply(loyalty_tier)
dim_customer[['customer_id', 'gender', 'age_band', 'loyalty_tier']].to_csv(
    DATA / 'dim_customer.csv', index=False
)
tier_dist = dim_customer['loyalty_tier'].value_counts().to_dict()
print(f"  dim_customer.csv: {len(dim_customer):,} rows — tiers: {tier_dist}")

# ── 6) dim_lease — format × size × prestige driven rent, staggered terms ────
#
# monthly_base_rent = rent_per_sqm × unit_size_sqm × prestige_mult × ±8% noise
#   rent_per_sqm: highest for Kiosks (tiny space, premium per sqm),
#                 lowest for Anchors (huge space, negotiate hard)
#   prestige_mult: Zorlu/Istinye Park 1.6×, value malls 0.7×
#
# rent_pct_of_sales: F&B formats highest (high turnover), Anchors lowest
#
# Lease terms: four staggered cohorts so not all 80 tenants expire together.
# Cohort 0 leases expired in 2021 — creates a realistic renewal scenario
# the agent can surface when asked about upcoming contract risks.

MALL_PRESTIGE = {
    'Zorlu Center':      'luxury',    # designer catchment, highest per-sqm
    'Istinye Park':      'luxury',
    'Kanyon':            'premium',
    'Emaar Square Mall': 'premium',
    'Forum Istanbul':    'standard',
    'Cevahir AVM':       'standard',
    'Mall of Istanbul':  'standard',
    'Metropol AVM':      'value',
    'Viaport Outlet':    'value',
    'Metrocity':         'value',
}
PRESTIGE_RENT_MULT = {'luxury': 1.60, 'premium': 1.20, 'standard': 1.00, 'value': 0.70}

# Monthly base rent per sqm (TRY 2020): kiosks highest per sqm, anchors lowest
FORMAT_RENT_PER_SQM = {
    'Kiosk':          900,
    'Food Court':     550,
    'Restaurant Pad': 380,
    'In-line':        290,
    'Anchor':         140,
}

# Rent % of sales range [min, max]: F&B highest turnover → highest %;
# Tech/Anchor lowest (high-ticket, low-margin, strong negotiating power)
FORMAT_RENT_PCT = {
    'Kiosk':          (0.08, 0.12),
    'Food Court':     (0.09, 0.12),
    'Restaurant Pad': (0.07, 0.10),
    'In-line':        (0.05, 0.09),
    'Anchor':         (0.03, 0.07),
}

# Four staggered cohorts — 25% of tenants in each, dates spread across 2018-2021
LEASE_COHORTS = [
    ('2018-01-01', '2021-12-31'),  # cohort 0: expired — triggers past-renewal analysis
    ('2020-06-01', '2023-09-30'),  # cohort 1: expiring Sep 2023 — "next 12 months" demo
    ('2020-01-01', '2024-12-31'),  # cohort 2: active, runs full data period
    ('2021-01-01', '2025-12-31'),  # cohort 3: newer tenants
]

lease_df = dim_tenant.merge(dim_mall[['mall_id', 'mall_name']], on='mall_id').copy()

pres_mult    = lease_df['mall_name'].map(MALL_PRESTIGE).map(PRESTIGE_RENT_MULT)
rent_per_sqm = lease_df['store_format'].map(FORMAT_RENT_PER_SQM)
hash_var     = lease_df['tenant_id'].apply(
    lambda t: 0.93 + (dhash(t, 'rent') % 15) / 100   # 0.93–1.07, ±7%
)
lease_df['monthly_base_rent'] = (
    rent_per_sqm * lease_df['unit_size_sqm'] * pres_mult * hash_var
).round(0).astype(int)

def _rent_pct(row):
    lo, hi = FORMAT_RENT_PCT[row['store_format']]
    frac   = (dhash(row['tenant_id'], 'pct') % 100) / 99
    return round(lo + frac * (hi - lo), 3)

lease_df['rent_pct_of_sales'] = lease_df.apply(_rent_pct, axis=1)

# Replacement tenants get a fresh 5-year lease from their effective_from date.
# Original tenants use the cohort-based schedule unchanged.
def _assign_lease_dates(row):
    if row['is_replacement']:
        start = row['effective_from']
        end   = start + pd.DateOffset(years=5)
        return str(start.date()), str(end.date())
    c = dhash(row['tenant_id'], 'cohort') % 4
    return LEASE_COHORTS[c][0], LEASE_COHORTS[c][1]

_lease_dates = lease_df.apply(_assign_lease_dates, axis=1, result_type='expand')
lease_df['lease_start_date'] = _lease_dates[0]
lease_df['lease_end_date']   = _lease_dates[1]

dim_lease = lease_df[['tenant_id', 'lease_start_date', 'lease_end_date',
                       'monthly_base_rent', 'rent_pct_of_sales']]
dim_lease.to_csv(DATA / 'dim_lease.csv', index=False)
print(f"  dim_lease.csv: {len(dim_lease)} rows "
      f"({lease_df['is_replacement'].sum()} replacement leases)")
_orig_cohort = lease_df[~lease_df['is_replacement']]['tenant_id'].apply(
    lambda t: dhash(t, 'cohort') % 4
)
cohort_dist = _orig_cohort.value_counts().sort_index().to_dict()
print(f"    Original lease cohorts: { {LEASE_COHORTS[k][0][:4]+'-'+LEASE_COHORTS[k][1][:4]: v for k,v in cohort_dist.items()} }")

# ── 7) dim_date — with Turkish public holidays ───────────────────────────────
tr = holidays.TR(years=range(2020, 2027))
dates = pd.date_range('2020-01-01', '2026-07-07', freq='D')
dim_date = pd.DataFrame({'date': dates})
dim_date['day_of_week']  = dim_date['date'].dt.day_name()
dim_date['is_weekend']   = dim_date['date'].dt.weekday >= 5
dim_date['is_holiday']   = dim_date['date'].dt.date.map(lambda d: d in tr)
dim_date['holiday_name'] = dim_date['date'].dt.date.map(lambda d: tr.get(d, ''))
dim_date['week_of_year'] = dim_date['date'].dt.isocalendar().week
dim_date['month']        = dim_date['date'].dt.month
dim_date['quarter']      = dim_date['date'].dt.quarter
dim_date['year']         = dim_date['date'].dt.year
dim_date.to_csv(DATA / 'dim_date.csv', index=False)
print(f"  dim_date.csv: {len(dim_date):,} rows")

# ── 8) fact_weather — Open-Meteo historical (Istanbul center) ───────────────
print("  Fetching weather from Open-Meteo (this may take a moment)...")
weather_url = (
    'https://archive-api.open-meteo.com/v1/archive'
    '?latitude=41.0082&longitude=28.9784'
    '&start_date=2020-01-01&end_date=2026-05-25'
    '&daily=temperature_2m_mean,precipitation_sum,weather_code'
    '&timezone=Europe%2FIstanbul'
)
try:
    r = requests.get(weather_url, timeout=60).json()
    wdf = pd.DataFrame({
        'date':             pd.to_datetime(r['daily']['time']),
        'temperature_c':    r['daily']['temperature_2m_mean'],
        'precipitation_mm': r['daily']['precipitation_sum'],
        'weather_code':     r['daily']['weather_code'],
    })
    fact_weather = pd.concat(
        [wdf.assign(mall_id=m) for m in dim_mall['mall_id']],
        ignore_index=True,
    )[['mall_id', 'date', 'temperature_c', 'precipitation_mm', 'weather_code']]
    fact_weather.to_csv(DATA / 'fact_weather.csv', index=False)
    print(f"  fact_weather.csv: {len(fact_weather):,} rows")
except Exception as e:
    print(f"  WARNING: Weather fetch failed ({e}). Skipping fact_weather.csv.")
    print("  Re-run prep_data.py when you have internet access.")

# ── 9) fact_foot_traffic — transaction-grounded hourly visitor estimates ──────
#
# Original source CSV covers Jan 2021 – Mar 2023; extended through yesterday
# by simulate_data.py (run daily). Our calendar spine starts Jan 2020.
# The 2020 period is backfilled with each mall's long-run average (busy_mult=1.0).
# See module docstring for full design rationale.
print("  Building fact_foot_traffic (transaction-grounded)...")

PEAK_HOURS              = list(range(10, 22))   # 12 hourly slots: 10am-9pm
BASE_VISITORS_PER_SQM  = 0.08                   # target ~20K/day for a 250K sqm mall

# Gaussian bell curve centred at 14:00 (2pm), σ = 3 h; normalised to sum = 1
hr_weights = np.array([np.exp(-0.5 * ((h - 14) / 3) ** 2) for h in PEAK_HOURS])
hr_weights /= hr_weights.sum()

# ── 9a) Actual daily transaction counts from source CSV ──────────────────────
txn_daily = (
    fact_transactions
    .assign(date_dt=lambda df: pd.to_datetime(df['date']))
    .groupby(['mall_id', 'date_dt'])
    .size()
    .rename('txn_count')
    .reset_index()
)

# ── 9b) Full mall × date spine (Jan 2020 – Jul 2026) ────────────────────────
all_dates = pd.date_range('2020-01-01', '2026-07-07', freq='D')
spine = pd.MultiIndex.from_product(
    [dim_mall['mall_id'].tolist(), all_dates],
    names=['mall_id', 'date_dt'],
).to_frame(index=False)

spine = spine.merge(txn_daily, on=['mall_id', 'date_dt'], how='left')
spine['txn_count'] = spine['txn_count'].fillna(0).astype(int)

# ── 9c) 28-day centred rolling average per mall → busyness multiplier ────────
spine = spine.sort_values(['mall_id', 'date_dt']).reset_index(drop=True)

# Rolling average uses only the 2021-2023 data (2020 stays 0 and is excluded
# from the window mean via min_periods).
spine['rolling_avg'] = (
    spine.groupby('mall_id')['txn_count']
    .transform(lambda s: s.rolling(28, min_periods=5, center=True).mean())
)
# For rows where rolling_avg is NaN (deep 2020 period), use the mall's global mean
mall_global_avg = (
    spine[spine['txn_count'] > 0]
    .groupby('mall_id')['txn_count']
    .mean()
)
spine['rolling_avg'] = spine.apply(
    lambda r: mall_global_avg.get(r['mall_id'], 10.0)
    if pd.isna(r['rolling_avg']) else r['rolling_avg'],
    axis=1,
).clip(lower=1.0)

# busy_mult: 2020 and zero-txn days default to 1.0 (average busyness)
spine['busy_mult'] = np.where(
    spine['txn_count'] > 0,
    (spine['txn_count'] / spine['rolling_avg']).clip(0.30, 3.0),
    1.0,
)

# ── 9d) Weekend and holiday browsing boosts ───────────────────────────────────
date_flags = (
    dim_date.set_index(dim_date['date'].dt.date)[['is_weekend', 'is_holiday']]
)
spine['_date_key'] = spine['date_dt'].dt.date
spine['is_weekend'] = spine['_date_key'].map(date_flags['is_weekend']).fillna(False)
spine['is_holiday'] = spine['_date_key'].map(date_flags['is_holiday']).fillna(False)

spine['browse_boost'] = 1.0
spine.loc[spine['is_weekend'], 'browse_boost'] = 1.40
# Holiday boost compounds on top of weekend boost where both are true
spine.loc[spine['is_holiday'], 'browse_boost'] = (
    spine.loc[spine['is_holiday'], 'browse_boost'] * 1.50
)

# ── 9e) GLA-based daily total visitors per mall-day ──────────────────────────
sqm_lookup = dim_mall.set_index('mall_id')['gross_leasable_sqm']
spine['base_daily'] = spine['mall_id'].map(sqm_lookup) * BASE_VISITORS_PER_SQM
spine['daily_total'] = (
    spine['base_daily'] * spine['busy_mult'] * spine['browse_boost']
).clip(lower=50).astype(int)

# ── 9f) Vectorised expansion to hourly rows ───────────────────────────────────
# Repeat each spine row 12 times (once per peak hour), assign hours in order.
spine_exp = spine.loc[spine.index.repeat(len(PEAK_HOURS))].reset_index(drop=True)
spine_exp['hour']       = np.tile(PEAK_HOURS, len(spine))
spine_exp['hr_weight']  = spine_exp['hour'].map(dict(zip(PEAK_HOURS, hr_weights)))
expected_hourly         = (spine_exp['daily_total'] * spine_exp['hr_weight']).clip(lower=0)
spine_exp['estimated_visits'] = np.random.poisson(expected_hourly).clip(min=0)

fact_foot_traffic = spine_exp[['mall_id', '_date_key', 'hour', 'estimated_visits']].rename(
    columns={'_date_key': 'date'}
)
fact_foot_traffic.to_csv(DATA / 'fact_foot_traffic.csv', index=False)
print(f"  fact_foot_traffic.csv: {len(fact_foot_traffic):,} rows")

# ── Quick sanity check ────────────────────────────────────────────────────────
daily_check = (
    fact_foot_traffic
    .groupby(['mall_id', 'date'])['estimated_visits']
    .sum()
    .reset_index()
    .merge(dim_mall[['mall_id', 'mall_name', 'gross_leasable_sqm']], on='mall_id')
)
print("\n  Foot traffic daily averages by mall (sanity check):")
summary = (
    daily_check
    .groupby('mall_name')['estimated_visits']
    .agg(['mean', 'min', 'max'])
    .astype(int)
    .sort_values('mean', ascending=False)
)
print(summary.to_string())

print(f"\nDone! 8 CSVs written to ./data/")
print("Run 'ls data/' to verify all 8 files are present.")
