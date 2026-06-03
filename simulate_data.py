"""
simulate_data.py — GoldenGate Retail AI synthetic dataset generator.

Generates 8 CSVs into data/ for 13 Bay Area malls, 500+ tenants, USD currency.
Date range: 2020-01-01 through 2026-05-27.

Target: ~900K–1.2M transactions with realistic Bay Area retail patterns.

Real events modeled
───────────────────
• COVID-19 lockdown          Mar 17 – Jun 14, 2020   ~0 transactions
• COVID partial reopen       Jun 15 – Dec 31, 2020   30–55% normal
• Vaccine recovery           Jan – Jun 2021           55–85% normal
• Full recovery              Jul 2021+                100%
• 2020 wildfire smoke        Aug 18 – Sep 15, 2020   −60% foot traffic
• Supply chain crunch        Oct 2021 – Mar 2022      −8% basket size
• Inflation impact           Jun 2022 – Jun 2023      −10% discretionary volume
• Tech layoffs (Bay Area)    Nov 2022 – Dec 2023      −15% at premium malls
• Westfield SF decline       Jan 2022 → Aug 2023      progressive close
• Atmospheric rivers         Dec 26 2022 – Mar 10 2023 +12% indoor malls
• Bay Area recovery          2024–2026                +8% growth

⚠️  DISCLAIMER: All data is completely synthetic and generated for
demonstration purposes only. Tenant names, revenue figures, transaction
data, and performance metrics are fictitious and do not represent the
actual financial performance of any real company, mall, or brand.

Run:
    python simulate_data.py
"""

import math
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

DATA = Path("data")
DATA.mkdir(exist_ok=True)

START = date(2020, 1, 1)
END   = date.today() - timedelta(days=1)  # always yesterday — never hardcoded

# ── US Holidays (California) ──────────────────────────────────────────────────
_US_HOLIDAYS = {
    # New Year's
    date(2020,1,1), date(2021,1,1), date(2022,1,1), date(2023,1,1),
    date(2024,1,1), date(2025,1,1), date(2026,1,1),
    # MLK Day
    date(2020,1,20), date(2021,1,18), date(2022,1,17), date(2023,1,16),
    date(2024,1,15), date(2025,1,20), date(2026,1,19),
    # Presidents Day
    date(2020,2,17), date(2021,2,15), date(2022,2,21), date(2023,2,20),
    date(2024,2,19), date(2025,2,17), date(2026,2,16),
    # Memorial Day
    date(2020,5,25), date(2021,5,31), date(2022,5,30), date(2023,5,29),
    date(2024,5,27), date(2025,5,26), date(2026,5,25),
    # July 4th
    date(2020,7,4), date(2021,7,4), date(2022,7,4), date(2023,7,4),
    date(2024,7,4), date(2025,7,4), date(2026,7,4),
    # Labor Day
    date(2020,9,7), date(2021,9,6), date(2022,9,5), date(2023,9,4),
    date(2024,9,2), date(2025,9,1), date(2026,9,7),
    # Thanksgiving
    date(2020,11,26), date(2021,11,25), date(2022,11,24), date(2023,11,23),
    date(2024,11,28), date(2025,11,27), date(2026,11,26),
    # Christmas
    date(2020,12,25), date(2021,12,25), date(2022,12,25), date(2023,12,25),
    date(2024,12,25), date(2025,12,25), date(2026,12,25),
}

# Black Fridays
_BLACK_FRIDAYS = {
    date(2020,11,27), date(2021,11,26), date(2022,11,25), date(2023,11,24),
    date(2024,11,29), date(2025,11,28), date(2026,11,27),
}
# Back to school (Aug 1–25 each year)
# Mother's Day (2nd Sunday of May)
_MOTHERS_DAY = {
    date(2020,5,10), date(2021,5,9), date(2022,5,8), date(2023,5,14),
    date(2024,5,12), date(2025,5,11), date(2026,5,10),
}
# Valentine's Day
_VALENTINES = {date(y, 2, 14) for y in range(2020, 2027)}


def _holiday_name(d: date) -> str:
    if d in _BLACK_FRIDAYS:         return "Black Friday"
    if d in _MOTHERS_DAY:           return "Mother's Day"
    if d in _VALENTINES:            return "Valentine's Day"
    if d.month == 12 and d.day in (24, 26):  return "Christmas Eve/Boxing"
    if d.month == 12 and d.day == 31:        return "New Year's Eve"
    if d in _US_HOLIDAYS:
        names = {(1,1):"New Year's Day",(7,4):"Independence Day",
                 (12,25):"Christmas Day",(11,26):"Thanksgiving",
                 (11,25):"Thanksgiving",(11,24):"Thanksgiving",
                 (11,23):"Thanksgiving",(11,28):"Thanksgiving",
                 (11,27):"Thanksgiving"}
        return names.get((d.month, d.day), "Federal Holiday")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. MALLS
# ─────────────────────────────────────────────────────────────────────────────
MALLS = [
    # id, name, city, tier, gla_sqft, lat, lon, opened_year
    ("m01","Westfield Valley Fair","San Jose","Premium Regional",1_800_000,37.3255,-121.9467,1956),
    ("m02","Stanford Shopping Center","Palo Alto","Luxury Open-Air",1_400_000,37.4432,-122.1688,1955),
    ("m03","Santana Row","San Jose","Lifestyle Premium",700_000,37.3201,-121.9490,2002),
    ("m04","Westfield San Francisco Centre","San Francisco","Urban Flagship",865_000,37.7847,-122.4072,1988),
    ("m05","Stonestown Galleria","San Francisco","Community Regional",910_000,37.7280,-122.4761,1952),
    ("m06","Bay Street Emeryville","Emeryville","Lifestyle Open-Air",420_000,37.8341,-122.2939,2002),
    ("m07","Great Mall","Milpitas","Value Outlet",1_500_000,37.4155,-121.8967,1994),
    ("m08","Hillsdale Shopping Center","San Mateo","Mid-tier Regional",1_100_000,37.5290,-122.3005,1954),
    ("m09","Stoneridge Shopping Center","Pleasanton","Mid-tier Regional",1_200_000,37.6960,-121.9283,1980),
    ("m10","Broadway Plaza","Walnut Creek","Mid-tier Open-Air",735_000,37.9016,-122.0653,1951),
    ("m11","Sunvalley Shopping Center","Concord","Value Regional",1_100_000,37.9577,-122.0188,1967),
    ("m12","Westfield Oakridge","San Jose","Mid-tier Regional",1_200_000,37.2503,-121.8662,1971),
    ("m13","San Francisco Premium Outlets","Livermore","Premium Outlets",800_000,37.6879,-121.8084,2012),
]

MALL_IDS   = [m[0] for m in MALLS]
MALL_NAMES = {m[0]: m[1] for m in MALLS}
MALL_CITIES= {m[0]: m[2] for m in MALLS}
MALL_TIERS = {m[0]: m[3] for m in MALLS}

# Revenue tier multiplier (base = mid-tier = 1.0)
MALL_REV_MULT = {
    "m01": 2.2,   # Valley Fair — top performer
    "m02": 2.5,   # Stanford — luxury, highest basket
    "m03": 2.0,   # Santana Row
    "m04": 1.8,   # Westfield SF (before decline)
    "m05": 1.0,   # Stonestown
    "m06": 0.9,   # Bay Street — smaller
    "m07": 0.85,  # Great Mall — value, high volume low price
    "m08": 1.1,   # Hillsdale
    "m09": 1.1,   # Stoneridge
    "m10": 1.3,   # Broadway Plaza
    "m11": 0.75,  # Sunvalley — value
    "m12": 1.0,   # Oakridge
    "m13": 1.4,   # SF Premium Outlets — premium discount
}

# Dataset scale factor — keeps the demo dataset at ~1.5M rows.
# Apply to BOTH transactions AND rents so rent-to-sales ratios stay realistic.
_TXN_SCALE  = 0.01   # 1% of real-world transaction volume
_RENT_SCALE = 0.01   # same factor on monthly rent → realistic rent-to-sales %

# Is this mall open-air or enclosed?
MALL_OPENAIR = {"m02","m03","m06","m10","m13"}

# Westfield SF closure timeline
_SF_CLOSE_START  = date(2022, 1, 1)   # start of visible decline
_SF_CLOSE_ANCHOR = date(2022, 6, 1)   # Nordstrom announces exit
_SF_CLOSE_END    = date(2023, 8, 15)  # keys handed to lender — zero revenue


# ─────────────────────────────────────────────────────────────────────────────
# 2. BRAND CATALOG
# ─────────────────────────────────────────────────────────────────────────────
# Each brand: (name, category, subcategory, store_format,
#              base_monthly_txns, base_avg_ticket_usd, monthly_rent_usd,
#              tier_presence)  ← tier_presence: min tier level to include
#   Tier levels: 1=value, 2=mid, 3=premium, 4=luxury
#   mall tiers: value=1, mid=2, premium/lifestyle=3, luxury=4
MALL_TIER_LEVEL = {
    "m01":3,"m02":4,"m03":4,"m04":3,"m05":2,"m06":2,
    "m07":1,"m08":2,"m09":2,"m10":3,"m11":1,"m12":2,"m13":3,
}

# (name, category, subcategory, format, monthly_txns, avg_ticket, monthly_rent, min_tier)
BRAND_CATALOG = [
    # ── Anchors ──────────────────────────────────────────────────────────────
    ("Macy's","Department Store","Anchor","Anchor",18000,65,95000,1),
    ("Nordstrom","Department Store","Anchor","Anchor",14000,120,145000,2),
    ("Bloomingdale's","Department Store","Anchor","Anchor",10000,180,160000,3),
    ("Neiman Marcus","Department Store","Luxury Anchor","Anchor",5000,350,180000,4),
    ("JCPenney","Department Store","Anchor","Anchor",12000,55,60000,1),
    ("Target","Mass Retail","Anchor","Anchor",22000,45,70000,1),
    ("Nordstrom Rack","Apparel","Off-Price","Anchor",9000,50,55000,2),

    # ── Fashion Apparel ──────────────────────────────────────────────────────
    ("Zara","Apparel","Fast Fashion","In-line",3500,68,35000,2),
    ("H&M","Apparel","Fast Fashion","In-line",4200,42,28000,1),
    ("Uniqlo","Apparel","Basics","In-line",3000,55,32000,2),
    ("Gap","Apparel","Casual","In-line",2800,48,22000,1),
    ("Old Navy","Apparel","Value Casual","In-line",3800,38,20000,1),
    ("Banana Republic","Apparel","Business Casual","In-line",2200,72,28000,2),
    ("J.Crew","Apparel","Preppy Casual","In-line",2000,75,30000,2),
    ("Express","Apparel","Work & Play","In-line",2400,58,24000,2),
    ("Forever 21","Apparel","Fast Fashion","In-line",3600,28,18000,1),
    ("Urban Outfitters","Apparel","Indie Casual","In-line",2600,52,26000,2),
    ("Free People","Apparel","Bohemian","In-line",1800,85,28000,3),
    ("Anthropologie","Apparel","Eclectic","In-line",1600,95,32000,3),
    ("Madewell","Apparel","Denim & Casual","In-line",1900,82,30000,3),
    ("Levi's","Apparel","Denim & Jeans","In-line",2200,72,28000,2),
    ("Everlane","Apparel","Sustainable Basics","In-line",1400,78,26000,3),
    ("Allbirds","Footwear","Sustainable Sneakers","In-line",1200,120,28000,3),
    ("Warby Parker","Eyewear","Direct-to-Consumer","In-line",900,195,22000,2),
    ("FIGS","Apparel","Medical Scrubs","Kiosk",700,80,12000,2),

    # ── Luxury ──────────────────────────────────────────────────────────────
    ("Louis Vuitton","Luxury","Handbags & Fashion","In-line",600,1200,180000,4),
    ("Gucci","Luxury","Fashion & Accessories","In-line",550,900,170000,4),
    ("Tiffany & Co.","Luxury","Jewelry","In-line",480,650,150000,4),
    ("Hermès","Luxury","Fashion & Leather","In-line",320,1800,200000,4),
    ("Balmain","Luxury","Ready-to-Wear","In-line",280,1100,160000,4),
    ("Coach","Luxury","Accessible Luxury","In-line",1400,320,65000,3),
    ("Kate Spade","Luxury","Accessible Luxury","In-line",1200,280,55000,3),
    ("Michael Kors","Luxury","Accessible Luxury","In-line",1500,250,52000,3),
    ("Tory Burch","Luxury","Lifestyle","In-line",1100,280,55000,3),
    ("Salvatore Ferragamo","Luxury","Italian Fashion","In-line",380,720,130000,4),
    ("Versace","Luxury","Italian Fashion","In-line",320,850,145000,4),

    # ── Fitness & Activewear ─────────────────────────────────────────────────
    ("lululemon","Fitness","Premium Activewear","In-line",2800,118,52000,2),
    ("Athleta","Fitness","Women's Activewear","In-line",2200,85,42000,2),
    ("Vuori","Fitness","Premium Activewear","In-line",1800,95,38000,3),
    ("Alo Yoga","Fitness","Luxury Activewear","In-line",1600,110,40000,3),
    ("Gymshark","Fitness","Performance Activewear","In-line",1400,65,30000,2),
    ("Nike","Footwear","Athletic Footwear","In-line",3200,88,45000,2),
    ("Adidas","Footwear","Athletic Footwear","In-line",2800,80,42000,2),
    ("New Balance","Footwear","Athletic Footwear","In-line",2000,95,35000,2),
    ("On Running","Footwear","Performance Running","In-line",1500,145,35000,3),
    ("Hoka","Footwear","Performance Running","In-line",1200,155,32000,3),
    ("REI","Sporting Goods","Outdoor Gear","Anchor",4500,110,75000,2),
    ("SoulCycle","Fitness","Boutique Studio","In-line",1200,32,30000,3),
    ("Equinox","Fitness","Premium Gym","Anchor",3500,185,90000,4),

    # ── Tech & Electronics ───────────────────────────────────────────────────
    ("Apple","Electronics","Consumer Electronics","In-line",3200,280,190000,2),
    ("Best Buy","Electronics","Consumer Electronics","Anchor",7000,220,95000,2),
    ("GameStop","Electronics","Gaming","In-line",2800,52,20000,1),
    ("Verizon","Telecom","Wireless","In-line",1600,75,18000,1),
    ("AT&T","Telecom","Wireless","In-line",1500,70,18000,1),
    ("T-Mobile","Telecom","Wireless","In-line",1700,65,16000,1),
    ("uBreakiFix","Electronics","Device Repair","Kiosk",1400,95,12000,1),

    # ── Beauty & Personal Care ───────────────────────────────────────────────
    ("Sephora","Beauty","Prestige Beauty","In-line",3800,72,48000,2),
    ("Ulta Beauty","Beauty","Mass & Prestige Beauty","In-line",3500,58,38000,2),
    ("Bath & Body Works","Beauty","Home & Body","In-line",3200,32,22000,1),
    ("Kiehl's","Beauty","Skincare","In-line",1200,65,25000,3),
    ("MAC Cosmetics","Beauty","Color Cosmetics","In-line",1600,45,22000,2),
    ("Glossier","Beauty","Direct-to-Consumer Skincare","In-line",1100,55,24000,3),
    ("The Ordinary","Beauty","Clinical Skincare","Kiosk",800,35,10000,2),
    ("Massage Envy","Wellness","Spa Services","In-line",1400,85,24000,2),
    ("European Wax Center","Beauty","Waxing Services","In-line",1600,48,18000,2),

    # ── Home & Lifestyle ────────────────────────────────────────────────────
    ("Williams-Sonoma","Home","Cookware & Kitchen","In-line",1800,120,55000,3),
    ("Pottery Barn","Home","Home Furnishings","In-line",1600,185,60000,3),
    ("West Elm","Home","Modern Home Decor","In-line",1400,175,52000,3),
    ("Crate & Barrel","Home","Home Decor","In-line",1500,195,58000,3),
    ("Restoration Hardware","Home","Luxury Home","Anchor",1200,420,85000,4),
    ("CB2","Home","Contemporary Home","In-line",1100,155,48000,3),
    ("Pottery Barn Kids","Home","Children's Furnishings","In-line",1200,110,42000,3),

    # ── Fast Casual & Coffee (Bay Area locals highlighted) ───────────────────
    ("Shake Shack","Food & Beverage","Fast Casual Burgers","Restaurant Pad",4800,15,28000,2),
    ("Five Guys","Food & Beverage","Fast Casual Burgers","Food Court",5200,14,22000,1),
    ("Sweetgreen","Food & Beverage","Fast Casual Salads","Food Court",4200,14,20000,2),
    ("Chipotle","Food & Beverage","Fast Casual Mexican","Restaurant Pad",6500,13,25000,1),
    ("Panda Express","Food & Beverage","Fast Casual Asian","Food Court",7000,11,18000,1),
    ("Jamba Juice","Food & Beverage","Smoothies & Juice","Kiosk",3000,9,12000,1),
    ("Starbucks","Food & Beverage","Coffee","Kiosk",8500,7,22000,1),
    ("Philz Coffee","Food & Beverage","Bay Area Craft Coffee","Restaurant Pad",5500,8,24000,2),
    ("Blue Bottle Coffee","Food & Beverage","Bay Area Craft Coffee","Restaurant Pad",4800,9,26000,2),
    ("Boudin SF Bakery","Food & Beverage","SF Sourdough & Bakery","Restaurant Pad",4500,12,22000,2),
    ("Ike's Love & Sandwiches","Food & Beverage","Bay Area Sandwiches","Restaurant Pad",3800,13,18000,2),
    ("Super Duper Burgers","Food & Beverage","Bay Area Burgers","Restaurant Pad",4200,14,20000,2),
    ("Gott's Roadside","Food & Beverage","Bay Area Roadside","Restaurant Pad",3500,16,22000,3),
    ("In-N-Out Burger","Food & Beverage","Fast Food Burgers","Restaurant Pad",8500,10,20000,1),
    ("The Cheesecake Factory","Food & Beverage","Casual Dining","Restaurant Pad",6500,28,45000,2),
    ("P.F. Chang's","Food & Beverage","Asian Casual Dining","Restaurant Pad",4500,32,40000,2),
    ("BJ's Restaurant","Food & Beverage","Casual Dining","Restaurant Pad",5000,28,38000,2),
    ("California Pizza Kitchen","Food & Beverage","Casual Dining","Restaurant Pad",4800,22,35000,2),
    ("Yard House","Food & Beverage","Bar & Grill","Restaurant Pad",5500,28,42000,3),
    ("Auntie Anne's","Food & Beverage","Soft Pretzels","Kiosk",3800,7,10000,1),
    ("Wetzel's Pretzels","Food & Beverage","Soft Pretzels","Kiosk",3200,7,9000,1),
    ("Cinnabon","Food & Beverage","Bakery","Kiosk",2800,7,9000,1),
    ("Peet's Coffee","Food & Beverage","Coffee","Kiosk",5200,8,14000,2),
    ("Nothing Bundt Cakes","Food & Beverage","Bakery","In-line",2200,18,16000,2),
    ("Din Tai Fung","Food & Beverage","Taiwanese Casual Dining","Restaurant Pad",3200,38,42000,3),
    ("85°C Bakery Cafe","Food & Beverage","Taiwanese Bakery & Coffee","In-line",4500,8,18000,2),
    ("Boba Guys","Food & Beverage","Bay Area Bubble Tea","Kiosk",3500,8,12000,2),
    ("Pressed Juicery","Food & Beverage","Cold Press Juice","Kiosk",2000,12,10000,3),
    ("Gyu-Kaku","Food & Beverage","Japanese BBQ","Restaurant Pad",2800,45,38000,3),
    ("Kura Revolving Sushi","Food & Beverage","Revolving Sushi Bar","Restaurant Pad",3500,28,35000,2),
    ("Ippudo","Food & Beverage","Ramen","Restaurant Pad",2500,22,30000,3),
    ("Dave's Hot Chicken","Food & Beverage","Fast Casual Chicken","Restaurant Pad",4200,13,22000,2),
    ("Crumbl Cookies","Food & Beverage","Artisan Cookies","In-line",3800,12,16000,2),
    ("Beard Papa's","Food & Beverage","Cream Puffs & Pastry","Kiosk",2800,8,10000,1),

    # ── Entertainment ────────────────────────────────────────────────────────
    ("AMC Theatres","Entertainment","Movie Theater","Anchor",12000,17,80000,2),
    ("Regal Cinemas","Entertainment","Movie Theater","Anchor",10000,16,72000,2),
    ("Dave & Buster's","Entertainment","Arcade & Bar","Anchor",8000,42,85000,2),
    ("Round1 Bowling","Entertainment","Bowling & Arcade","Anchor",7000,28,65000,2),
    ("Bowlero","Entertainment","Upscale Bowling","Anchor",6500,32,70000,2),

    # ── Children & Family ────────────────────────────────────────────────────
    ("Build-A-Bear Workshop","Children","Interactive Toy","In-line",2200,32,20000,1),
    ("Lego Store","Children","Toy Retail","In-line",2800,48,28000,2),
    ("Learning Express Toys","Children","Educational Toys","In-line",1800,40,18000,2),
    ("Carter's","Children","Children's Apparel","In-line",2400,38,18000,1),
    ("Gap Kids","Children","Children's Apparel","In-line",1800,42,18000,2),
    ("OshKosh B'gosh","Children","Children's Apparel","In-line",2000,35,16000,1),
    ("Gymboree","Children","Children's Apparel","In-line",1600,45,18000,2),

    # ── Jewelry ─────────────────────────────────────────────────────────────
    ("Kay Jewelers","Jewelry","Jewelry","In-line",1200,280,20000,1),
    ("Zales","Jewelry","Jewelry","In-line",1100,260,18000,1),
    ("Pandora","Jewelry","Charm Jewelry","In-line",2200,80,22000,2),
    ("Tiffany & Co. Outlet","Jewelry","Luxury Jewelry Outlet","In-line",1400,280,38000,3),

    # ── Footwear ─────────────────────────────────────────────────────────────
    ("Foot Locker","Footwear","Athletic Footwear","In-line",3200,78,28000,1),
    ("DSW","Footwear","Discount Shoe Warehouse","In-line",3800,62,32000,2),
    ("Steve Madden","Footwear","Trendy Footwear","In-line",2400,82,28000,2),
    ("Aldo","Footwear","Fashion Footwear","In-line",2000,75,22000,2),
    ("Vans","Footwear","Skate & Lifestyle","In-line",2800,68,25000,2),
    ("Converse","Footwear","Classic Sneakers","In-line",2400,70,22000,2),

    # ── Accessories ──────────────────────────────────────────────────────────
    ("Sunglass Hut","Accessories","Sunglasses","Kiosk",1400,180,14000,1),
    ("Oakley","Accessories","Sport Sunglasses","In-line",1200,165,18000,2),
    ("Fossil","Accessories","Watches & Leather","In-line",1100,145,18000,2),
    ("Claire's","Accessories","Fashion Jewelry","In-line",2400,18,10000,1),
    ("Spencer's","Accessories","Pop Culture","In-line",2200,22,12000,1),
    ("Kendra Scott","Accessories","Lifestyle Jewelry","In-line",1600,95,24000,3),
    ("Alex and Ani","Accessories","Charm Jewelry","In-line",1200,45,16000,2),

    # ── Health & Services ────────────────────────────────────────────────────
    ("GNC","Health","Supplements","Kiosk",1600,48,14000,1),
    ("The Vitamin Shoppe","Health","Supplements","In-line",1400,52,16000,1),
    ("Walgreens","Health","Drug Store","Anchor",4500,28,45000,1),
    ("LensCrafters","Health","Optical","In-line",900,320,18000,2),
    ("Great Clips","Services","Hair Salon","In-line",2000,28,12000,1),
    ("Sport Clips","Services","Men's Haircuts","In-line",1800,28,12000,2),
    ("Drybar","Services","Blowout Bar","In-line",1600,48,18000,3),
    ("Nail Garden","Services","Nail Salon","In-line",2200,42,14000,1),

    # ── Books & Gifts ────────────────────────────────────────────────────────
    ("Barnes & Noble","Books","Bookstore","Anchor",3800,22,42000,2),
    ("Things Remembered","Gifts","Personalized Gifts","Kiosk",800,45,10000,1),
    ("Hallmark Gold Crown","Gifts","Cards & Gifts","In-line",1200,18,12000,1),
    ("Yankee Candle","Home","Candles","In-line",1400,28,14000,1),

    # ── Outlet / Value (mainly Great Mall, Sunvalley, Livermore) ─────────────
    ("Saks Fifth Avenue OFF 5TH","Apparel","Luxury Outlet","In-line",3500,55,32000,3),
    ("Last Call by Neiman Marcus","Apparel","Luxury Outlet","In-line",2800,65,35000,3),
    ("Gap Outlet","Apparel","Outlet","In-line",3200,32,16000,1),
    ("Banana Republic Factory","Apparel","Factory Outlet","In-line",2800,38,18000,2),
    ("Nike Factory Store","Footwear","Factory Outlet","In-line",4200,55,28000,2),
    ("Adidas Outlet","Footwear","Factory Outlet","In-line",3800,45,24000,2),
    ("Coach Outlet","Luxury","Accessible Luxury Outlet","In-line",3200,180,35000,2),
    ("Michael Kors Outlet","Luxury","Accessible Luxury Outlet","In-line",3500,150,32000,2),
    ("Kate Spade Outlet","Luxury","Accessible Luxury Outlet","In-line",3000,165,30000,2),
    ("Brooks Brothers","Apparel","Classic American","In-line",1400,155,30000,2),
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. ASSIGN TENANTS TO MALLS
# ─────────────────────────────────────────────────────────────────────────────
def _assign_tenants():
    """
    Returns list of (tenant_id, brand_idx, mall_id) for all active stores.
    ~40-50 stores per mall.
    """
    assignments = []

    for mall_id in MALL_IDS:
        tier = MALL_TIER_LEVEL[mall_id]
        is_outlet = "Outlet" in MALL_TIERS[mall_id] or "Value" in MALL_TIERS[mall_id]
        is_openair = mall_id in MALL_OPENAIR

        # Outlet malls prefer outlet brands; enclosed malls prefer standard
        eligible = []
        for idx, brand in enumerate(BRAND_CATALOG):
            name, cat, subcat, fmt, txns, ticket, rent, min_tier = brand

            # Tier filter
            if tier < min_tier:
                continue

            # Outlet logic: outlet brands only at outlet/value malls
            is_outlet_brand = "Outlet" in subcat or "Factory" in subcat or "Off-Price" in subcat
            if is_outlet_brand and not is_outlet:
                continue
            if is_outlet and is_outlet_brand:
                eligible.append(idx)
                continue

            # Studios/gyms don't fit every mall
            if fmt == "Anchor" and mall_id in ("m03","m06","m10","m13"):
                if cat not in ("Department Store","Mass Retail","Entertainment","Sporting Goods"):
                    continue

            eligible.append(idx)

        # Shuffle and pick target count
        target = random.randint(38, 48)
        random.shuffle(eligible)
        selected = eligible[:target]

        for idx in selected:
            tid = f"t_{mall_id}_{idx:03d}"
            assignments.append((tid, idx, mall_id))

    return assignments


ASSIGNMENTS = _assign_tenants()
print(f"Total active store slots: {len(ASSIGNMENTS)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. DIM_MALL
# ─────────────────────────────────────────────────────────────────────────────
print("Building dim_mall...")
dim_mall_rows = []
for m in MALLS:
    mid, name, city, tier, gla, lat, lon, opened = m
    dim_mall_rows.append({
        "mall_id": mid,
        "mall_name": name,
        "city": city,
        "state": "CA",
        "country": "USA",
        "tier": tier,
        "gross_leasable_sqft": gla,
        "latitude": lat,
        "longitude": lon,
        "opened_year": opened,
    })
pd.DataFrame(dim_mall_rows).to_csv(DATA / "dim_mall.csv", index=False)
print(f"  dim_mall: {len(dim_mall_rows)} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 5. DIM_TENANT + DIM_LEASE (with SCD Type 2 replacements)
# ─────────────────────────────────────────────────────────────────────────────
print("Building dim_tenant + dim_lease...")

# Mall closure date for Westfield SF
SF_TENANT_CLOSE = date(2023, 8, 15)

dim_tenant_rows = []
dim_lease_rows  = []

# Stores that had tenant replacements (to add SCD Type 2 variety)
# These brand indexes will have a "closed + replaced" scenario
# About 15% of stores get a replacement
_replaceable_brands = {
    "Forever 21", "JCPenney", "GameStop", "Spencer's", "Things Remembered",
    "Gymboree", "Brooks Brothers", "Walgreens", "LensCrafters", "Hallmark Gold Crown",
    "Gap", "Express", "OshKosh B'gosh", "Hot Topic", "Borders"
}

REPLACEMENT_BRANDS = [
    ("Skims","Apparel","Intimates & Loungewear","In-line",2000,68,28000),
    ("Faherty","Apparel","Sustainable Casual","In-line",1600,88,26000),
    ("Patagonia","Sporting Goods","Outdoor Apparel","In-line",2200,95,32000),
    ("Arc'teryx","Sporting Goods","Technical Outdoor","In-line",1800,280,40000),
    ("Knot Standard","Apparel","Made-to-Measure","In-line",700,450,30000),
    ("Aesop","Beauty","Luxury Skincare","In-line",1100,65,28000),
    ("Madhappy","Apparel","Wellness Streetwear","In-line",1400,85,26000),
    ("Vuori","Fitness","Premium Activewear","In-line",1800,95,38000),
    ("Stanley","Home","Drinkware","Kiosk",1600,42,12000),
    ("Carhartt WIP","Apparel","Workwear Lifestyle","In-line",1800,75,24000),
    ("Glossier","Beauty","Direct-to-Consumer Skincare","In-line",1100,55,24000),
    ("Mejuri","Jewelry","Fine Jewelry","In-line",1400,180,26000),
    ("Alo Yoga","Fitness","Luxury Activewear","In-line",1600,110,40000),
    ("Sol de Janeiro","Beauty","Body Care","Kiosk",1200,38,12000),
    ("Savage X Fenty","Apparel","Lingerie","In-line",1800,55,26000),
]

ACTIVE_UNTIL = date(2026, 7, 31)

for (tid, brand_idx, mall_id) in ASSIGNMENTS:
    brand = BRAND_CATALOG[brand_idx]
    bname, cat, subcat, fmt, base_txns, avg_ticket, monthly_rent, _ = brand

    is_sf = (mall_id == "m04")

    # Effective dates
    eff_from = date(2019, random.randint(1, 12), 1)
    if is_sf:
        eff_to = SF_TENANT_CLOSE
    else:
        eff_to = ACTIVE_UNTIL

    # SCD Type 2: some brands closed mid-period and got replaced
    do_replace = (bname in _replaceable_brands and not is_sf
                  and random.random() < 0.25)

    if do_replace:
        close_year  = random.randint(2021, 2023)
        close_month = random.randint(1, 12)
        close_date  = date(close_year, close_month, 1)
        eff_to      = close_date

    dim_tenant_rows.append({
        "tenant_id":      tid,
        "tenant_name":    bname,
        "mall_id":        mall_id,
        "category":       cat,
        "subcategory":    subcat,
        "unit_size_sqm":  int(random.uniform(800, 4500) * 0.0929),  # sqft → sqm
        "store_format":   fmt,
        "effective_from": eff_from,
        "effective_to":   eff_to,
        "is_replacement": False,
    })

    # Lease for original tenant
    lease_start = eff_from
    lease_end   = eff_to + timedelta(days=365)
    rent_mult   = MALL_REV_MULT[mall_id]
    actual_rent = monthly_rent * max(0.7, min(1.5, rent_mult * random.uniform(0.85, 1.15))) * _RENT_SCALE
    dim_lease_rows.append({
        "tenant_id":         tid,
        "lease_start_date":  lease_start,
        "lease_end_date":    lease_end,
        "monthly_base_rent": round(actual_rent, 2),
        "rent_pct_of_sales": round(random.uniform(5, 12), 2),
    })

    # Add replacement tenant
    if do_replace:
        rbrand = random.choice(REPLACEMENT_BRANDS)
        rbname, rcat, rsubcat, rfmt, rtxns, rticket, rrent = rbrand
        r_tid    = tid + "_r"
        r_from   = close_date + timedelta(days=random.randint(30, 90))
        dim_tenant_rows.append({
            "tenant_id":      r_tid,
            "tenant_name":    rbname,
            "mall_id":        mall_id,
            "category":       rcat,
            "subcategory":    rsubcat,
            "unit_size_sqm":  int(random.uniform(800, 3000) * 0.0929),
            "store_format":   rfmt,
            "effective_from": r_from,
            "effective_to":   ACTIVE_UNTIL,
            "is_replacement": True,
        })
        r_actual_rent = rrent * max(0.7, min(1.5, rent_mult * random.uniform(0.85, 1.15))) * _RENT_SCALE
        dim_lease_rows.append({
            "tenant_id":         r_tid,
            "lease_start_date":  r_from,
            "lease_end_date":    r_from + timedelta(days=365 * 5),
            "monthly_base_rent": round(r_actual_rent, 2),
            "rent_pct_of_sales": round(random.uniform(5, 10), 2),
        })

pd.DataFrame(dim_tenant_rows).to_csv(DATA / "dim_tenant.csv", index=False)
pd.DataFrame(dim_lease_rows).to_csv(DATA / "dim_lease.csv", index=False)
print(f"  dim_tenant: {len(dim_tenant_rows)} rows")
print(f"  dim_lease:  {len(dim_lease_rows)} rows")

# Build lookup: tenant_id → brand profile (including replacements)
TENANT_PROFILE = {}
for row in dim_tenant_rows:
    tid = row["tenant_id"]
    # Find brand txns and ticket
    bname = row["tenant_name"]
    # Try original brand catalog first
    match = next((b for b in BRAND_CATALOG if b[0] == bname), None)
    if match:
        _, _, _, _, txns, ticket, _, _ = match
    else:
        match_r = next((b for b in REPLACEMENT_BRANDS if b[0] == bname), None)
        if match_r:
            _, _, _, _, txns, ticket, _ = match_r
        else:
            txns, ticket = 1200, 55
    TENANT_PROFILE[tid] = {
        "mall_id":    row["mall_id"],
        "base_txns":  txns,
        "avg_ticket": ticket,
        "eff_from":   row["effective_from"],
        "eff_to":     row["effective_to"],
        "category":   row["category"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. DIM_DATE
# ─────────────────────────────────────────────────────────────────────────────
print("Building dim_date...")
all_dates = []
d = START
while d <= END:
    all_dates.append(d)
    d += timedelta(days=1)

dim_date_rows = []
for d in all_dates:
    is_hol    = d in _US_HOLIDAYS or d in _BLACK_FRIDAYS or d in _MOTHERS_DAY or d in _VALENTINES
    hol_name  = _holiday_name(d)
    back2school = (d.month == 8 and 1 <= d.day <= 25)
    if back2school and not is_hol:
        is_hol   = False
        hol_name = "Back to School"
    dim_date_rows.append({
        "date":         d,
        "day_of_week":  d.strftime("%A"),
        "is_weekend":   d.weekday() >= 5,
        "is_holiday":   is_hol,
        "holiday_name": hol_name,
        "week_of_year": d.isocalendar()[1],
        "month":        d.month,
        "quarter":      (d.month - 1) // 3 + 1,
        "year":         d.year,
    })
pd.DataFrame(dim_date_rows).to_csv(DATA / "dim_date.csv", index=False)
print(f"  dim_date: {len(dim_date_rows)} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 7. EVENT MULTIPLIER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def _volume_mult(d: date, mall_id: str) -> float:
    """Return a (0–2.5) multiplier for transaction volume on date d at mall_id."""
    m = 1.0

    # ── COVID ────────────────────────────────────────────────────────────────
    if date(2020, 3, 17) <= d <= date(2020, 6, 14):
        m *= 0.04   # Near-total shutdown
    elif date(2020, 6, 15) <= d <= date(2020, 8, 17):
        m *= 0.42   # Phase 2: limited capacity
    elif date(2020, 8, 18) <= d <= date(2020, 9, 15):
        m *= 0.20   # Wildfire smoke + COVID (orange sky days)
    elif date(2020, 9, 16) <= d <= date(2020, 12, 31):
        m *= 0.55   # Phase 3 + holiday restrictions
    elif date(2021, 1, 1) <= d <= date(2021, 3, 31):
        m *= 0.62
    elif date(2021, 4, 1) <= d <= date(2021, 6, 30):
        m *= 0.75   # Vaccine rollout, cautious reopening
    elif date(2021, 7, 1) <= d <= date(2021, 12, 31):
        m *= 0.92   # Near-full reopening but habits changed

    # ── Supply chain crunch ──────────────────────────────────────────────────
    if date(2021, 10, 1) <= d <= date(2022, 3, 31):
        m *= 0.93   # Inventory shortages → fewer items to sell

    # ── Inflation impact on discretionary spending ───────────────────────────
    if date(2022, 6, 1) <= d <= date(2023, 6, 30):
        m *= 0.91

    # ── Tech layoffs (stronger at premium Bay Area malls) ────────────────────
    if date(2022, 11, 1) <= d <= date(2023, 12, 31):
        if mall_id in ("m01","m02","m03","m09","m10"):
            m *= 0.87

    # ── Atmospheric rivers (Dec 2022 – Mar 2023) boost indoor, hurt open-air ─
    if date(2022, 12, 26) <= d <= date(2023, 3, 10):
        if mall_id in MALL_OPENAIR:
            m *= 0.80   # Open-air malls suffer in heavy rain
        else:
            m *= 1.12   # Enclosed malls get a boost

    # ── Westfield SF Centre decline & closure ────────────────────────────────
    if mall_id == "m04":
        if d >= _SF_CLOSE_END:
            return 0.0  # Fully closed
        elif d >= _SF_CLOSE_START:
            total_days  = (_SF_CLOSE_END - _SF_CLOSE_START).days
            elapsed     = (d - _SF_CLOSE_START).days
            decline     = elapsed / total_days
            # Accelerating decline: anchor tenants leave first, then cascade
            m *= max(0.0, 1.0 - (decline ** 1.4))

    # ── Recovery 2024 – 2026 ─────────────────────────────────────────────────
    if date(2024, 1, 1) <= d:
        months_into_recovery = (d.year - 2024) * 12 + d.month
        m *= min(1.18, 1.0 + months_into_recovery * 0.006)  # Gradual recovery

    return max(0.0, m)


def _seasonal_mult(d: date) -> float:
    """Seasonal + day-of-week multiplier."""
    dow   = d.weekday()  # 0=Mon … 6=Sun
    month = d.month
    day   = d.day

    # Day-of-week
    dow_mult = {0:0.72, 1:0.70, 2:0.73, 3:0.76, 4:0.88, 5:1.45, 6:1.38}[dow]

    # Monthly seasonality (US retail patterns)
    month_mult = {
        1:0.82, 2:0.80, 3:0.85, 4:0.87, 5:0.92,
        6:0.88, 7:0.85, 8:0.98, 9:0.87, 10:0.95,
        11:1.28, 12:1.55
    }[month]

    # Holiday spikes
    if d in _BLACK_FRIDAYS:
        return dow_mult * month_mult * 2.8
    if d in _MOTHERS_DAY:
        return dow_mult * month_mult * 1.55
    if d in _VALENTINES:
        return dow_mult * month_mult * 1.35
    if d in _US_HOLIDAYS:
        return dow_mult * month_mult * 1.45
    if d.month == 12 and d.day in (22, 23, 24):
        return dow_mult * month_mult * 2.0
    if d.month == 8 and 1 <= d.day <= 25:
        return dow_mult * month_mult * 1.12  # Back to school

    return dow_mult * month_mult


# ─────────────────────────────────────────────────────────────────────────────
# 8. FACT_TRANSACTIONS
# ─────────────────────────────────────────────────────────────────────────────
print("Building fact_transactions (this takes 1-2 minutes)...")

# Build customer pool
NUM_CUSTOMERS = 45_000
CUSTOMER_IDS = [f"C{100000 + i}" for i in range(NUM_CUSTOMERS)]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Apple Pay", "Cash", "Buy Now Pay Later"]
PAYMENT_WEIGHTS = [0.42, 0.25, 0.18, 0.08, 0.07]

invoice_counter = 1_000_000
txn_rows = []

# Group tenants by mall for efficient iteration
mall_tenants: dict[str, list[str]] = {mid: [] for mid in MALL_IDS}
for (tid, _, mall_id) in ASSIGNMENTS:
    mall_tenants[mall_id].append(tid)
    # Add replacement tenants
    if tid + "_r" in TENANT_PROFILE:
        mall_tenants[mall_id].append(tid + "_r")

TOTAL_DAYS = (END - START).days + 1
checkpoint_days = set(range(0, TOTAL_DAYS, 200))

d = START
day_num = 0
while d <= END:
    if day_num in checkpoint_days:
        print(f"  ... {d} ({len(txn_rows):,} txns so far)")

    for mall_id in MALL_IDS:
        v_mult = _volume_mult(d, mall_id)
        if v_mult < 0.001:
            continue  # skip this mall for today, do NOT advance d here

        s_mult = _seasonal_mult(d)
        mall_mult = MALL_REV_MULT[mall_id]

        for tid in mall_tenants[mall_id]:
            prof = TENANT_PROFILE.get(tid)
            if not prof:
                continue
            if d < prof["eff_from"] or d > prof["eff_to"]:
                continue

            # Expected transactions today for this tenant
            daily_base = prof["base_txns"] / 30.0 * _TXN_SCALE
            expected   = daily_base * v_mult * s_mult * mall_mult

            # Poisson-draw actual transactions
            n_txns = max(0, np.random.poisson(max(0.01, expected)))
            if n_txns == 0:
                continue

            base_ticket = prof["avg_ticket"]
            category    = prof["category"]
            mall_id_prof = prof["mall_id"]

            for _ in range(n_txns):
                qty        = np.random.choice([1,1,1,2,2,3], p=[0.50,0.25,0.12,0.08,0.03,0.02])
                # Price varies ±25% around base
                unit_price = round(base_ticket * random.uniform(0.75, 1.28), 2)
                total      = round(qty * unit_price, 2)
                payment    = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS)[0]
                cid        = random.choice(CUSTOMER_IDS)

                txn_rows.append({
                    "invoice_no":     f"INV{invoice_counter:08d}",
                    "tenant_id":      tid,
                    "mall_id":        mall_id_prof,
                    "customer_id":    cid,
                    "date":           d,
                    "category":       category,
                    "quantity":       qty,
                    "unit_price":     unit_price,
                    "total_amount":   total,
                    "payment_method": payment,
                })
                invoice_counter += 1

    d += timedelta(days=1)
    day_num += 1

df_txns = pd.DataFrame(txn_rows)
df_txns.to_csv(DATA / "fact_transactions.csv", index=False)
print(f"  fact_transactions: {len(df_txns):,} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 9. FACT_WEATHER (Bay Area realistic patterns)
# ─────────────────────────────────────────────────────────────────────────────
print("Building fact_weather...")

# Bay Area weather by city archetype:
# SF: cool, foggy, wet winters; inland (SJ/Pleasanton/Concord): warmer, drier
# Livermore: hottest summers
CITY_WEATHER = {
    "San Francisco":  {"base_temp_c": 13.5, "temp_amp": 5.0,  "rain_season_mm": 12, "fog_bias": 2.0},
    "Palo Alto":      {"base_temp_c": 14.8, "temp_amp": 8.0,  "rain_season_mm": 8,  "fog_bias": 0.5},
    "San Jose":       {"base_temp_c": 15.5, "temp_amp": 9.0,  "rain_season_mm": 7,  "fog_bias": 0.3},
    "Emeryville":     {"base_temp_c": 14.2, "temp_amp": 6.0,  "rain_season_mm": 9,  "fog_bias": 1.0},
    "Milpitas":       {"base_temp_c": 15.2, "temp_amp": 9.5,  "rain_season_mm": 6,  "fog_bias": 0.2},
    "San Mateo":      {"base_temp_c": 14.0, "temp_amp": 7.0,  "rain_season_mm": 9,  "fog_bias": 0.8},
    "Pleasanton":     {"base_temp_c": 15.8, "temp_amp": 11.0, "rain_season_mm": 7,  "fog_bias": 0.0},
    "Walnut Creek":   {"base_temp_c": 16.0, "temp_amp": 11.5, "rain_season_mm": 7,  "fog_bias": 0.0},
    "Concord":        {"base_temp_c": 15.8, "temp_amp": 12.0, "rain_season_mm": 6,  "fog_bias": 0.0},
    "Livermore":      {"base_temp_c": 16.5, "temp_amp": 13.0, "rain_season_mm": 5,  "fog_bias": 0.0},
}

# Atmospheric rivers: extra heavy rain Dec 2022 – Mar 2023
_ATMO_RIVER = (date(2022, 12, 26), date(2023, 3, 10))

weather_rows = []
for m in MALLS:
    mid, mname, city, *_ = m
    wc = CITY_WEATHER.get(city, CITY_WEATHER["San Jose"])
    d = START
    while d <= END:
        doy_rad = 2 * math.pi * (d.timetuple().tm_yday / 365.0)
        # Temperature: annual cycle (coldest Jan, warmest Sep for SF, Aug for inland)
        temp_c  = wc["base_temp_c"] + wc["temp_amp"] * math.sin(doy_rad - math.pi * 0.45)
        temp_c += random.gauss(0, 1.5)

        # Precipitation: rainy Nov–Apr, dry May–Oct
        rain_season = d.month in (11, 12, 1, 2, 3, 4)
        if rain_season:
            base_rain = wc["rain_season_mm"]
        else:
            base_rain = 0.5

        # Atmospheric rivers: 3-4x normal rain
        if _ATMO_RIVER[0] <= d <= _ATMO_RIVER[1]:
            base_rain *= 3.5

        # Daily rain (exponential distribution — most days dry)
        if random.random() < (0.45 if rain_season else 0.05):
            precip = round(random.expovariate(1.0 / base_rain), 1)
        else:
            precip = 0.0

        # Weather code (simplified WMO codes)
        if precip > 15:     wcode = 61   # heavy rain
        elif precip > 5:    wcode = 51   # moderate rain
        elif precip > 0:    wcode = 50   # light rain
        elif wc["fog_bias"] > 1.0 and d.month in (6,7,8) and random.random() < 0.4:
            wcode = 45   # fog (SF summer)
        else:
            wcode = 0    # clear

        weather_rows.append({
            "mall_id":         mid,
            "date":            d,
            "temperature_c":   round(temp_c, 1),
            "precipitation_mm": precip,
            "weather_code":    wcode,
        })
        d += timedelta(days=1)

df_weather = pd.DataFrame(weather_rows)
df_weather.to_csv(DATA / "fact_weather.csv", index=False)
print(f"  fact_weather: {len(df_weather):,} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 10. FACT_FOOT_TRAFFIC
# ─────────────────────────────────────────────────────────────────────────────
print("Building fact_foot_traffic...")

# Hourly traffic profiles (indexed 10am–9pm = hours 10–21)
WEEKDAY_PROFILE = {10:0.04,11:0.06,12:0.11,13:0.10,14:0.08,15:0.09,16:0.10,
                   17:0.11,18:0.12,19:0.12,20:0.07}
WEEKEND_PROFILE = {10:0.05,11:0.09,12:0.13,13:0.13,14:0.11,15:0.10,16:0.10,
                   17:0.10,18:0.09,19:0.07,20:0.03}

# Base daily visits by mall (proportional to GLA and tier)
BASE_DAILY_VISITS = {
    "m01":28000,"m02":22000,"m03":18000,"m04":24000,"m05":14000,
    "m06":10000,"m07":20000,"m08":15000,"m09":16000,"m10":14000,
    "m11":13000,"m12":15000,"m13":18000,
}

traffic_rows = []
for mid in MALL_IDS:
    base = BASE_DAILY_VISITS[mid]
    d = START
    while d <= END:
        v_mult = _volume_mult(d, mid)
        s_mult = _seasonal_mult(d)
        total_visits = int(base * v_mult * s_mult * random.uniform(0.90, 1.10))

        profile = WEEKEND_PROFILE if d.weekday() >= 5 else WEEKDAY_PROFILE
        for hour, frac in profile.items():
            visits = int(total_visits * frac * random.uniform(0.85, 1.15))
            traffic_rows.append({
                "mall_id":         mid,
                "date":            d,
                "hour":            hour,
                "estimated_visits": max(0, visits),
            })
        d += timedelta(days=1)

df_traffic = pd.DataFrame(traffic_rows)
df_traffic.to_csv(DATA / "fact_foot_traffic.csv", index=False)
print(f"  fact_foot_traffic: {len(df_traffic):,} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 11. DIM_CUSTOMER
# ─────────────────────────────────────────────────────────────────────────────
print("Building dim_customer...")

AGE_BANDS   = ["18-24","25-34","35-44","45-54","55-64","65+"]
AGE_WEIGHTS = [0.14,0.28,0.24,0.17,0.11,0.06]
GENDERS     = ["Female","Male","Non-binary"]
G_WEIGHTS   = [0.52,0.44,0.04]
LOYALTY     = ["Bronze","Silver","Gold","Platinum"]
L_WEIGHTS   = [0.42,0.30,0.18,0.10]

dim_cust_rows = []
for cid in CUSTOMER_IDS:
    dim_cust_rows.append({
        "customer_id":  cid,
        "gender":       random.choices(GENDERS, weights=G_WEIGHTS)[0],
        "age_band":     random.choices(AGE_BANDS, weights=AGE_WEIGHTS)[0],
        "loyalty_tier": random.choices(LOYALTY, weights=L_WEIGHTS)[0],
    })
pd.DataFrame(dim_cust_rows).to_csv(DATA / "dim_customer.csv", index=False)
print(f"  dim_customer: {len(dim_cust_rows):,} rows")


# ─────────────────────────────────────────────────────────────────────────────
# 12. FORECAST CACHE (empty — populated by BigQuery ML after load)
# ─────────────────────────────────────────────────────────────────────────────
pd.DataFrame(columns=["mall_id","forecast_date","forecast_revenue",
                       "lower_90","upper_90","cached_at"]).to_csv(
    DATA / "forecast_cache.csv", index=False)

print(f"\n✅ All CSVs written to {DATA}/")
print(f"   Transactions: {len(df_txns):,}")
print(f"   Tenants:      {len(dim_tenant_rows):,}  (active + historical)")
print(f"   Malls:        {len(dim_mall_rows)}")
print(f"\nNext: python load_bigquery.py")
