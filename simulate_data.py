"""
simulate_data.py — Extend customer_shopping_data.csv: March 9 2023 → May 27 2026.

Run from the mallpulse/ project root (venv active):
    python simulate_data.py

Reads customer_shopping_data.csv, appends simulated rows, and overwrites the
file in-place.  Then re-run prep_data.py to regenerate the 8 data/ CSVs.

Schema preserved
────────────────
invoice_no, customer_id, gender, age, category, quantity, price,
payment_method, invoice_date, shopping_mall

Design decisions
────────────────

PRICE INFLATION (TRY)
  Turkey's CPI path 2023-2026 is encoded as quarterly cumulative multipliers
  anchored to the Q1-2023 price level in the original dataset.
  Technology and imported goods carry a category-specific premium (USD-linked).

  Source: TCMB official CPI releases + IMF projections to 2026.

  Q1-2023 baseline = 1.0
  Peak inflation ~75% YoY reached May 2024 (multiplier 2.08)
  Disinflation from late 2024; by May 2026 cumulative ~3.43x original level.

VOLUME EVENTS (chronological)
  • Post-Feb 6 earthquake shock   Mar–Jun 2023  −12% volume
  • Turkish election uncertainty  Apr–May 2023  −7%  (compounded with above)
  • Post-election normalization   Jun–Sep 2023  −4%
  • Gaza conflict onset           Oct 2023–Mar 2024  −3%
  • Turkish local elections       Mar–Apr 2024  −4%
  • Economic stabilization        Jul–Dec 2024  +1%
  • Disinflation recovery         2025          +4%
  • Continued recovery            2026 YTD      +7%

SEASONALITY (mirrors prep_data.py MONTH_MULT)
  Dec +30%, Nov +15%, Jan +10%, Jul/Aug −15%, etc.
  Weekend +40%, Turkish public holiday ×1.50
  Ramadan: daytime F&B −10%, clothing/shoes pre-Eid boost
  Eid al-Fitr: overall +25%, clothing/shoes/toys spike
  Black Friday (4th Fri Nov): +35% overall

TOURISM RECOVERY
  Record 2023 and 2024 tourism seasons → Souvenir & F&B get a +10% category uplift.

PAYMENT METHOD SHIFT
  High inflation drove instalment credit adoption.  Credit-card share rises
  ~5 pp over 2023-2025, partially reversing in 2026 as rates ease.

INVOICE / CUSTOMER IDs
  7-digit numbers (I1000001+, C1000001+) — no overlap with original 6-digit IDs.
"""

import numpy as np
import pandas as pd
import holidays
from pathlib import Path

np.random.seed(2025)

# ── Load existing CSV (keep raw strings for dates — no re-formatting risk) ───
print("Loading customer_shopping_data.csv...")
orig = pd.read_csv('customer_shopping_data.csv')
_dates_parsed = pd.to_datetime(orig['invoice_date'], dayfirst=True)
last_date = _dates_parsed.max()
print(f"  {len(orig):,} existing rows  |  last date: {last_date.date()}")

# ── Mall distribution ────────────────────────────────────────────────────────
MALLS   = ['Mall of Istanbul', 'Kanyon', 'Metrocity', 'Metropol AVM', 'Istinye Park',
           'Zorlu Center', 'Cevahir AVM', 'Forum Istanbul', 'Viaport Outlet', 'Emaar Square Mall']
MALL_W  = np.array([0.2005, 0.1993, 0.1509, 0.1022, 0.0983,
                    0.0510, 0.0502, 0.0497, 0.0494, 0.0484])
MALL_W  /= MALL_W.sum()

# ── Category distribution ────────────────────────────────────────────────────
CATEGORIES = ['Clothing', 'Cosmetics', 'Food & Beverage', 'Toys',
              'Shoes', 'Souvenir', 'Technology', 'Books']
CAT_W      = np.array([0.3468, 0.1518, 0.1486, 0.1014, 0.1009, 0.0503, 0.0502, 0.0501])
CAT_W     /= CAT_W.sum()

# Base unit prices (TRY, Q1-2023 level).
# LINE TOTAL = unit_price × quantity  — matching original CSV convention.
BASE_UNIT = {
    'Technology':      1050.00,
    'Shoes':            600.17,
    'Clothing':         300.08,
    'Cosmetics':         40.66,
    'Toys':              35.84,
    'Books':             15.15,
    'Souvenir':          11.73,
    'Food & Beverage':    5.23,
}

# Category-specific extra inflation multiplier on top of macro CPI.
# Electronics and imported goods priced in USD → stronger TRY depreciation pass-through.
CAT_PRICE_EXTRA = {
    'Technology':      1.18,
    'Shoes':           1.08,
    'Books':           1.10,
    'Cosmetics':       1.06,
    'Toys':            1.08,
    'Clothing':        1.04,
    'Food & Beverage': 1.12,
    'Souvenir':        1.00,
}

# ── Macro price inflation: cumulative CPI multiplier per (year, quarter) ─────
# Anchored to Q1-2023 = 1.00.  Based on TCMB CPI data + IMF projections.
PRICE_MULT = {
    (2023, 1): 1.00,
    (2023, 2): 1.12,   # TCMB starts hiking rates June 2023
    (2023, 3): 1.30,   # September CPI rebound; YoY ~60%
    (2023, 4): 1.50,   # December: YoY ~65%
    (2024, 1): 1.78,
    (2024, 2): 2.08,   # Peak: May 2024 ~75% YoY
    (2024, 3): 2.38,   # Rate hikes biting but cumulative still rising
    (2024, 4): 2.62,
    (2025, 1): 2.85,   # Disinflation underway; ~30% YoY
    (2025, 2): 3.05,
    (2025, 3): 3.18,
    (2025, 4): 3.28,
    (2026, 1): 3.36,
    (2026, 2): 3.43,   # ~12% YoY by mid-2026
    (2026, 3): 3.50,   # Q3-2026: continued slow disinflation
}

# ── Monthly volume seasonality (mirrors prep_data.py MONTH_MULT) ─────────────
MONTH_MULT = {
    1: 1.10, 2: 0.90, 3: 0.95, 4: 1.00, 5: 1.00, 6: 0.95,
    7: 0.85, 8: 0.85, 9: 1.00, 10: 1.05, 11: 1.15, 12: 1.30,
}

# ── Turkish public holidays (2023-2026) ──────────────────────────────────────
TR_HOLS = holidays.TR(years=range(2023, 2027))

# ── Ramadan & Eid al-Fitr calendar ───────────────────────────────────────────
# (ramadan_start, ramadan_end_inclusive, eid_start, eid_end_inclusive)
_RAMADAN_DEF = [
    ('2023-03-23', '2023-04-20', '2023-04-21', '2023-04-23'),
    ('2024-03-11', '2024-04-08', '2024-04-09', '2024-04-11'),
    ('2025-03-01', '2025-03-29', '2025-03-30', '2025-04-01'),
    ('2026-02-18', '2026-03-17', '2026-03-18', '2026-03-20'),
]
_ramadan_days: set = set()
_eid_days: set     = set()
for rs, re, es, ee in _RAMADAN_DEF:
    for d in pd.date_range(rs, re, freq='D'):
        _ramadan_days.add(d.date())
    for d in pd.date_range(es, ee, freq='D'):
        _eid_days.add(d.date())

# ── Volume event modifiers ────────────────────────────────────────────────────
# (start, end, volume_multiplier)
_EVENTS = [
    ('2023-03-09', '2023-06-30', 0.88),   # post-earthquake economic shock
    ('2023-04-01', '2023-05-28', 0.93),   # Turkish election uncertainty (compounded)
    ('2023-06-01', '2023-09-30', 0.96),   # post-election normalization, still cautious
    ('2023-10-07', '2024-03-31', 0.97),   # Gaza conflict: slight Gulf tourist dip
    ('2024-03-01', '2024-04-15', 0.96),   # Turkish local elections (CHP wins Istanbul)
    ('2024-07-01', '2024-12-31', 1.01),   # H2-2024: stabilization, lira firming
    ('2025-01-01', '2025-12-31', 1.04),   # 2025: disinflation → real income recovery
    ('2026-01-01', '2099-12-31', 1.07),   # 2026+: continued normalization
]
EVENTS = [(pd.Timestamp(s), pd.Timestamp(e), m) for s, e, m in _EVENTS]


def _event_mult(dt: pd.Timestamp) -> float:
    m = 1.0
    for s, e, v in EVENTS:
        if s <= dt <= e:
            m *= v
    return m


def _price_mult(dt: pd.Timestamp) -> float:
    q = (dt.month - 1) // 3 + 1
    return PRICE_MULT.get((dt.year, q), PRICE_MULT[(2026, 2)])


# Payment weight baseline: Cash 44.7%, Credit Card 35.1%, Debit Card 20.2%
_PAY_BASE = np.array([0.4469, 0.3512, 0.2019])
PAYMENTS  = ['Cash', 'Credit Card', 'Debit Card']

def _pay_weights(dt: pd.Timestamp) -> np.ndarray:
    """
    High inflation (2023-2025) drives instalment credit adoption → credit-card share
    rises ~5 pp.  Partially reverses in 2026 as rates ease.
    """
    progress = np.clip((dt.year - 2023 + (dt.month - 1) / 12) / 3.0, 0.0, 1.0)
    shift = 0.05 * progress
    w = _PAY_BASE.copy()
    w[0] -= shift    # Cash down
    w[1] += shift    # Credit Card up
    return np.clip(w, 0.01, None) / np.clip(w, 0.01, None).sum()


GENDERS = ['Female', 'Male']
GEN_W   = np.array([0.5988, 0.4012])


def _cat_weights(dt: pd.Timestamp, in_ramadan: bool, is_eid: bool) -> np.ndarray:
    """Adjust category mix for Ramadan/Eid, Black Friday, December gifts, tourism."""
    w   = CAT_W.copy()
    idx = {c: i for i, c in enumerate(CATEGORIES)}

    if in_ramadan:
        w[idx['Food & Beverage']] *= 0.90  # daytime fasting suppresses F&B
        w[idx['Clothing']]        *= 1.05  # pre-Eid fashion shopping begins
        w[idx['Shoes']]           *= 1.05

    if is_eid:
        w[idx['Clothing']]        *= 1.30
        w[idx['Shoes']]           *= 1.20
        w[idx['Toys']]            *= 1.15
        w[idx['Food & Beverage']] *= 1.10  # family restaurant meals

    if dt.month == 11:                     # Black Friday
        w[idx['Technology']]      *= 1.20
        w[idx['Clothing']]        *= 1.12
        w[idx['Shoes']]           *= 1.10

    if dt.month == 12:                     # Gift season
        w[idx['Toys']]            *= 1.25
        w[idx['Technology']]      *= 1.15

    # Tourism recovery 2023+: souvenir and F&B uplift from international visitors
    if dt.year >= 2023:
        w[idx['Souvenir']]        *= 1.12
        w[idx['Food & Beverage']] *= 1.05

    return w / w.sum()


def _is_black_friday(dt: pd.Timestamp) -> bool:
    """4th Friday of November."""
    return dt.month == 11 and dt.weekday() == 4 and 22 <= dt.day <= 28


# ── Main simulation ───────────────────────────────────────────────────────────
# Auto-detect start date so re-running always picks up from where it left off.
_existing_dates = pd.to_datetime(orig['invoice_date'], dayfirst=True)
_last_date      = _existing_dates.max()
SIM_START       = _last_date + pd.Timedelta(days=1)
SIM_END         = pd.Timestamp('today').normalize() - pd.Timedelta(days=1)  # yesterday
BASE_DAILY      = 125   # average transactions per day (all malls combined)

if SIM_START > SIM_END:
    print(f"  Data already covers up to {_last_date.date()} — nothing to simulate.")
    raise SystemExit(0)

print(f"  Resuming from {SIM_START.date()} (last existing date: {_last_date.date()})")

# Derive 7-digit ID counters from whatever is already in the file — avoids
# collisions if the script is re-run after a partial extension.
_7d_inv  = orig['invoice_no'].str.extract(r'^I(\d{7,})$',  expand=False).dropna().astype(int)
_7d_cust = orig['customer_id'].str.extract(r'^C(\d{7,})$', expand=False).dropna().astype(int)
inv_counter  = int(_7d_inv.max())  + 1 if len(_7d_inv)  else 1_000_001
cust_counter = int(_7d_cust.max()) + 1 if len(_7d_cust) else 1_000_001

rows     = []
all_dates = pd.date_range(SIM_START, SIM_END, freq='D')
print(f"Simulating {SIM_START.date()} → {SIM_END.date()} ({len(all_dates):,} days)...")

for dt in all_dates:
    dkey = dt.date()

    # ── Daily volume ─────────────────────────────────────────────────────────
    vol = float(BASE_DAILY)
    vol *= MONTH_MULT[dt.month]

    is_weekend  = dt.weekday() >= 5
    is_holiday  = dkey in TR_HOLS
    in_ramadan  = dkey in _ramadan_days
    is_eid      = dkey in _eid_days
    is_bf       = _is_black_friday(dt)

    if is_weekend:  vol *= 1.40
    if is_holiday:  vol *= 1.50
    if in_ramadan:  vol *= 0.97   # slight overall suppression
    if is_eid:      vol *= 1.25
    if is_bf:       vol *= 1.35

    vol *= _event_mult(dt)

    n = max(1, int(np.random.poisson(vol)))

    # ── Per-transaction draws ─────────────────────────────────────────────────
    pmult  = _price_mult(dt)
    pay_w  = _pay_weights(dt)
    cat_w  = _cat_weights(dt, in_ramadan, is_eid)

    malls   = np.random.choice(MALLS,      size=n, p=MALL_W)
    cats    = np.random.choice(CATEGORIES, size=n, p=cat_w)
    qtys    = np.random.randint(1, 6, size=n)          # 1-5, uniform
    genders = np.random.choice(GENDERS,    size=n, p=GEN_W)
    ages    = np.random.randint(18, 70,    size=n)
    pays    = np.random.choice(PAYMENTS,   size=n, p=pay_w)

    # Jitter drawn once per day (small ±5% noise)
    jitters = 1.0 + np.random.uniform(-0.05, 0.05, size=n)

    # Date string: D/M/YYYY (dayfirst=True, no zero-padding) — matches original CSV
    date_str = f"{dkey.day}/{dkey.month}/{dkey.year}"

    for i in range(n):
        cat        = cats[i]
        qty        = int(qtys[i])
        unit_price = BASE_UNIT[cat] * pmult * CAT_PRICE_EXTRA[cat] * jitters[i]
        line_total = round(unit_price * qty, 2)

        rows.append({
            'invoice_no':     f'I{inv_counter}',
            'customer_id':    f'C{cust_counter}',
            'gender':         genders[i],
            'age':            int(ages[i]),
            'category':       cat,
            'quantity':       qty,
            'price':          line_total,
            'payment_method': pays[i],
            'invoice_date':   date_str,
            'shopping_mall':  malls[i],
        })
        inv_counter  += 1
        cust_counter += 1

new_df = pd.DataFrame(rows)
print(f"  Generated {len(new_df):,} new rows  |  "
      f"{len(new_df) / len(all_dates):.1f} avg txns/day")

# ── Validation ────────────────────────────────────────────────────────────────
print("\nSimulated data quick-check:")
print(f"  Date range  : {new_df['invoice_date'].iloc[0]} → {new_df['invoice_date'].iloc[-1]}")

_new_dates = pd.to_datetime(new_df['invoice_date'], dayfirst=True)
_dow       = _new_dates.dt.day_name().value_counts()
_wkend     = (_dow.get('Saturday', 0) + _dow.get('Sunday', 0)) / len(new_df)
print(f"  Weekend share: {_wkend:.1%}  (expected 27–31%)")

print("\n  Category distribution (%):")
print((new_df['category'].value_counts(normalize=True) * 100).round(1).to_string())

print("\n  Payment method distribution (%):")
print((new_df['payment_method'].value_counts(normalize=True) * 100).round(1).to_string())

# Price sanity: spot-check Q1-2023 vs Q2-2026 Technology mean
_tech   = new_df[new_df['category'] == 'Technology']
_tech_d = pd.to_datetime(_tech['invoice_date'], dayfirst=True)
_q1_23  = _tech[_tech_d < '2023-07-01']['price'].mean()
_q2_26  = _tech[_tech_d >= '2026-01-01']['price'].mean()
print(f"\n  Technology mean price  Q1-2023: ₺{_q1_23:,.0f}  |  Q2-2026: ₺{_q2_26:,.0f}"
      f"  (ratio {_q2_26/_q1_23:.2f}× — expect ~{PRICE_MULT[(2026,2)] * CAT_PRICE_EXTRA['Technology']:.2f}×)")

# ── Append and save ───────────────────────────────────────────────────────────
print(f"\nCombining {len(orig):,} original + {len(new_df):,} simulated rows...")
extended = pd.concat([orig, new_df], ignore_index=True)
extended.to_csv('customer_shopping_data.csv', index=False)
print(f"Saved {len(extended):,} total rows to customer_shopping_data.csv")
print("\nNext step: re-run prep_data.py to regenerate the 8 data/ CSVs.")
