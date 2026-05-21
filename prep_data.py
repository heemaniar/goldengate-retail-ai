"""
prep_data.py - Augment the Istanbul Mall dataset for MallPulse.
Run from the mallpulse/ project root with the venv active:
    python prep_data.py

Requires: customer_shopping_data.csv in the same directory.
Produces: 7 CSVs in ./data/
"""
import os
import pandas as pd
import requests
import holidays
from pathlib import Path

DATA = Path('data')
DATA.mkdir(exist_ok=True)

# ── 1) Load raw Istanbul data ────────────────────────────────────────────────
print("Loading customer_shopping_data.csv...")
raw = pd.read_csv('customer_shopping_data.csv')
raw['invoice_date'] = pd.to_datetime(raw['invoice_date'], dayfirst=True)
print(f"  {len(raw):,} rows | columns: {list(raw.columns)}")

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
                f't_{chosen.lower().replace(" ", "_").replace("&", "").replace("__","_")}'
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
# The raw dataset uses shopping_mall names matching MALL_GEO keys
mall_name_to_id = dict(zip(dim_mall['mall_name'], dim_mall['mall_id']))
tenant_key = {
    (r['mall_id'], r['category']): r['tenant_id']
    for _, r in dim_tenant.iterrows()
}

raw['mall_id'] = raw['shopping_mall'].map(mall_name_to_id)
raw['tenant_id'] = raw.apply(
    lambda r: tenant_key.get((r['mall_id'], r['category'])), axis=1
)
raw['total_amount'] = raw['quantity'] * raw['price']

fact_transactions = raw.rename(
    columns={'price': 'unit_price', 'invoice_date': 'date'}
)[[
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
dim_customer['age_band'] = dim_customer['age'].apply(age_band)
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
        'tenant_id': tenant_id,
        'lease_start_date': '2020-01-01',
        'lease_end_date': '2025-12-31',
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
    # Replicate the same weather row for all 10 malls
    fact_weather = pd.concat(
        [wdf.assign(mall_id=m) for m in dim_mall['mall_id']],
        ignore_index=True
    )[['mall_id', 'date', 'temperature_c', 'precipitation_mm', 'weather_code']]
    fact_weather.to_csv(DATA / 'fact_weather.csv', index=False)
    print(f"  fact_weather.csv: {len(fact_weather):,} rows")
except Exception as e:
    print(f"  WARNING: Weather fetch failed ({e}). Skipping fact_weather.csv.")
    print("  Re-run prep_data.py when you have internet access to get the weather data.")

print("\nDone! CSVs written to ./data/")
print("Run 'ls data/' to verify all 7 files are present.")
