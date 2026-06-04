"""
tests/test_accuracy.py — GoldenGate Retail AI accuracy regression tests (FIX 3).

GoldenGate's accuracy guarantees (COUNT(DISTINCT) for uniques, SUM÷SUM for
basket, no fabrication on empty periods) currently live only as *prompt
instructions* in agents/mallpulse/sub_agents.py. A model swap (Gemini 3 preview
→ GA, or a fallback to 2.5) could silently regress them.

These tests assert the *invariant relationship* that distinguishes the correct
SQL semantics from the naive/wrong ones — computed at runtime, NOT pinned to a
hardcoded figure. That keeps them green across a full warehouse rebuild (a new
RNG seed changes every absolute value but not the relationships below):
  - unique customers: COUNT(DISTINCT) is strictly LESS than SUM(daily uniques)
    — guaranteed whenever any customer shops on >1 day.
  - avg basket: SUM÷SUM is in a sane retail range AND diverges from
    AVG(per-day basket) — the average-of-averages bug.
  - distinct cities: structural (mall roster) → fixed at 10.
  - out-of-range years: structural (date range) → zero rows, no fabrication.

They hit BigQuery directly (read-only) rather than driving the LLM agent — that
keeps them deterministic and CI-friendly. So they protect against *data drift*
and against anyone rewriting a reference query into the wrong form; they do NOT
invoke the agent, so they don't prove the agent itself picks the right SQL.
If BigQuery credentials are unavailable the whole module is skipped.

Run:  pytest -v tests/test_accuracy.py
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── BigQuery availability gate ────────────────────────────────────────────────
# Skip the entire module (rather than error) when there are no credentials,
# so offline runs / CI without GCP auth stay green.

def _scalar(sql: str):
    """Run a single-value query and return the scalar, or raise."""
    from tools.bigquery_tools import _get_client
    job = _get_client().query(sql)
    rows = list(job.result(max_results=1))
    return rows[0][0] if rows else None


@pytest.fixture(scope="module", autouse=True)
def _require_bigquery():
    try:
        _scalar("SELECT 1")
    except Exception as e:  # noqa: BLE001 — any auth/network failure → skip
        pytest.skip(f"BigQuery not reachable, skipping accuracy regression: {e}")


# ── Trap 1: unique customers must be COUNT(DISTINCT), not SUM(aggregate) ───────

class TestUniqueCustomers:

    def test_count_distinct_is_strictly_below_naive_daily_sum(self):
        """Invariant: COUNT(DISTINCT customer_id) < SUM(daily unique_customers).

        SUM(unique_customers) from the aggregate table double-counts anyone who
        shops on more than one day, so it is always strictly larger than the true
        distinct count. This holds for any RNG seed — no hardcoded figure to
        re-baseline. If the naive sum ever stops exceeding the distinct count,
        the double-count trap has become undetectable and this fails loudly.
        """
        distinct = _scalar(
            """
            SELECT COUNT(DISTINCT f.customer_id)
            FROM `mallpulse-hackathon.goldengate_core.fact_transactions` f
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%stanford%'
              AND f.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        )
        naive_sum = _scalar(
            """
            SELECT SUM(a.unique_customers)
            FROM `mallpulse-hackathon.goldengate_core.agg_mall_daily` a
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%stanford%'
              AND a.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        )
        assert distinct and distinct > 0, "no Stanford transactions in May 2026"
        assert naive_sum > distinct, (
            f"trap collapsed: SUM(daily uniques)={naive_sum} no longer exceeds "
            f"COUNT(DISTINCT)={distinct} — the double-count error is undetectable"
        )


# ── Trap 2: average basket must be SUM÷SUM, not AVG(avg_basket) ────────────────

class TestAverageBasket:

    def test_sum_over_count_is_sane_and_differs_from_avg_of_averages(self):
        """Invariant: the correct basket (SUM÷COUNT over transactions) is in a
        sane retail range AND diverges from AVG(per-day basket).

        AVG(per-day basket) is the average-of-averages bug — it weights every
        day equally regardless of volume, so it differs from the volume-weighted
        SUM÷SUM. No hardcoded value; both sides are computed at runtime.

        NOTE: the divergence margin is mall-dependent. Santana Row reliably
        diverges; if you re-point this at a low-variance mall the second assert
        could flake — keep it on a mall with meaningful daily volume swings.
        """
        correct = float(_scalar(
            """
            SELECT SUM(f.total_amount) / COUNT(DISTINCT f.invoice_no)
            FROM `mallpulse-hackathon.goldengate_core.fact_transactions` f
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%santana%'
              AND f.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        ))
        avg_of_daily = float(_scalar(
            """
            SELECT AVG(daily_basket) FROM (
                SELECT a.date, SUM(a.revenue) / SUM(a.transactions) AS daily_basket
                FROM `mallpulse-hackathon.goldengate_core.agg_tenant_daily` a
                JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
                WHERE LOWER(m.mall_name) LIKE '%santana%'
                  AND a.date BETWEEN '2026-05-01' AND '2026-05-31'
                GROUP BY a.date
            )
            """
        ))
        assert 5 < correct < 1000, f"basket ${correct:.2f} outside sane retail range"
        assert abs(correct - avg_of_daily) > 0.001 * correct, (
            f"methods coincide (SUM/SUM=${correct:.2f}, avg-of-avg=${avg_of_daily:.2f}); "
            f"average-of-averages trap not exercised at this mall"
        )


# ── Trap 3: distinct city count ────────────────────────────────────────────────

class TestDistinctCities:

    def test_distinct_city_count_is_10(self):
        cities = _scalar(
            "SELECT COUNT(DISTINCT city) "
            "FROM `mallpulse-hackathon.goldengate_core.dim_mall`"
        )
        assert cities == 10


# ── Trap 4: out-of-range years must return no data (no fabrication) ────────────

class TestNoDataForOutOfRangeYears:

    @pytest.mark.parametrize("year", [2018, 2031])
    def test_year_has_no_rows(self, year):
        n = _scalar(
            f"""
            SELECT COUNT(*)
            FROM `mallpulse-hackathon.goldengate_core.agg_mall_daily`
            WHERE EXTRACT(YEAR FROM date) = {year}
            """
        )
        assert n == 0, (
            f"{year} unexpectedly has {n} rows — an answer citing a revenue "
            f"figure for {year} would be fabricated."
        )
