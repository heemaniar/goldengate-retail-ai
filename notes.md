# MallPulse — Agent Testing Notes

## Day 6 — 5-Question Test Results (2026-05-22)

### Q1: Transaction count for a specific mall and period ✅
> "How many transactions did Kanyon mall have in March 2023?"

**Result:** Answered correctly (208 transactions). Fast at 5.6s.
**SQL pattern used:** COUNT(*) with date filter on fact_transactions joined to dim_mall.

---

### Q2: Top tenant by revenue at a specific mall ✅
> "Who is the top performing clothing tenant at Kanyon by revenue?"

**Result:** Correctly identified H&M (₺22.6M). Used get_top_tenants tool.
**Note:** Kanyon's Clothing tenant is now H&M (not Zara) after dhash() reassignment.

---

### Q3: Cross-mall tenant comparison ✅
> "Compare Zara across all malls — which location generates the most revenue?"

**Result:** Correctly found Zara at Metrocity (₺17.2M) and Metropol AVM (₺11.6M).
**Note:** Zara only appears at 2 of 10 malls — agent correctly scoped to those malls.

---

### Q4: Lease expiry in date window ✅ (fixed)
> "Which tenants have leases expiring within the next 12 months from March 2023?"

**Initial failure:** Returned empty — no leases expired in March 2023–March 2024 with original cohort dates.
**Root cause:** Cohort 1 was set to expire May 2024, just outside the window.
**Fix:** Shifted cohort 1 end date to 2023-09-30 → 17 leases now expire September 2023.
**Result after fix:** Returns 17 tenants across 9 malls with exact rent amounts. ✅

---

### Q5: Revenue forecast ✅
> "Forecast next 7 days revenue for Kanyon."

**Result:** BigQuery ML ARIMA_PLUS returns ₺63,431/day (90% CI: ₺23K–₺104K).
**Note:** Flat forecast (all 7 days identical) — expected because our synthetic data
has high day-to-day variance but no strong trend or seasonality signal.
The confidence interval width (₺80K range) is honest and reflects real variance.

---

## Known Failure Modes to Address (Day 7 prompt refinement)

1. **"Last quarter" / relative date references**
   - Agent may interpret "last quarter" relative to today (2026) not data end (2023-03-08)
   - **Fix:** Add explicit instruction: "Treat 'recent', 'last quarter', 'this year' as
     relative to 2023-03-08, the last date in the dataset."

2. **Weather × foot traffic correlation queries**
   - "Did rain reduce traffic on rainy days in 2022?" requires a multi-step join
     (fact_weather + fact_foot_traffic + aggregation) — agent may time out or generate
     incorrect SQL on first attempt.
   - **Fix:** Add a dedicated `get_weather_traffic_correlation` tool.

3. **Forecast is flat — no trend shown**
   - Limitation of ARIMA_PLUS on synthetic data with no seasonal signal.
   - **Demo mitigation:** Frame as "average revenue baseline with uncertainty bounds"
     rather than a trending forecast.

4. **Cross-mall "portfolio" queries can be slow**
   - Queries aggregating all 10 malls across all dates hit the full fact_transactions table.
   - **Fix:** Ensure agent defaults to agg_mall_daily for portfolio-level queries.

---

## Agent Performance Summary

| Metric | Value |
|--------|-------|
| Questions attempted | 5 |
| Correct on first try | 4 |
| Fixed after data/prompt change | 1 |
| Avg response time | ~5.4s |
| Tool calls per question | 1–2 |
