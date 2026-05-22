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
import numpy as np
import pandas as pd
import requests
import holidays
from pathlib import Path

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

mall_lookup = dict(zip(dim_mall['mall_name'], dim_mall['mall_id']))
tenants = []
for mall in dim_mall['mall_name']:
    for cat, names in TENANTS.items():
        chosen = names[hash((mall, cat)) % len(names)]
        tenants.append({
            'tenant_id': (
                f't_{chosen.lower().replace(" ", "_").replace("&", "").replace("__", "_")}'
                f'_{mall_lookup[mall]}'
            ),
            'tenant_name': chosen,
            'mall_id': mall_lookup[mall],
            'category': cat,
            'subcategory': cat,
            'unit_size_sqm': 100 + (hash((mall, cat)) % 400),
            'store_format': 'In-line',
        })

dim_tenant = pd.DataFrame(tenants)
dim_tenant.to_csv(DATA / 'dim_tenant.csv', index=False)
print(f"  dim_tenant.csv: {len(dim_tenant)} rows")

# ── 4) fact_transactions — map raw rows to tenant/mall IDs ──────────────────
mall_name_to_id = dict(zip(dim_mall['mall_name'], dim_mall['mall_id']))
tenant_key = {
    (r['mall_id'], r['category']): r['tenant_id']
    for _, r in dim_tenant.iterrows()
}

raw['mall_id']    = raw['shopping_mall'].map(mall_name_to_id)
raw['tenant_id']  = raw.apply(lambda r: tenant_key.get((r['mall_id'], r['category'])), axis=1)
raw['total_amount'] = raw['quantity'] * raw['price']

fact_transactions = raw.rename(columns={'price': 'unit_price', 'invoice_date': 'date'})[[
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

dim_customer = raw[['customer_id', 'gender', 'age']].drop_duplicates('customer_id').copy()
dim_customer['age_band']     = dim_customer['age'].apply(age_band)
dim_customer['loyalty_tier'] = 'Standard'
dim_customer[['customer_id', 'gender', 'age_band', 'loyalty_tier']].to_csv(
    DATA / 'dim_customer.csv', index=False
)
print(f"  dim_customer.csv: {len(dim_customer):,} rows")

# ── 6) dim_lease — synthetic but deterministic per tenant ───────────────────
def lease_for(tenant_id):
    rent = 8000 + (hash(tenant_id) % 12000)
    pct  = round(0.04 + (hash(tenant_id) % 10) / 200, 3)
    return {
        'tenant_id':         tenant_id,
        'lease_start_date':  '2020-01-01',
        'lease_end_date':    '2025-12-31',
        'monthly_base_rent': rent,
        'rent_pct_of_sales': pct,
    }

dim_lease = pd.DataFrame([lease_for(t) for t in dim_tenant['tenant_id']])
dim_lease.to_csv(DATA / 'dim_lease.csv', index=False)
print(f"  dim_lease.csv: {len(dim_lease)} rows")

# ── 7) dim_date — with Turkish public holidays ───────────────────────────────
tr = holidays.TR(years=range(2020, 2024))
dates = pd.date_range('2020-01-01', '2023-04-01', freq='D')
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
    '&start_date=2020-01-01&end_date=2023-04-01'
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
# Source CSV covers Jan 2021 – Mar 2023. Our calendar spine starts Jan 2020.
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

# ── 9b) Full mall × date spine (Jan 2020 – Apr 2023) ────────────────────────
all_dates = pd.date_range('2020-01-01', '2023-04-01', freq='D')
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
