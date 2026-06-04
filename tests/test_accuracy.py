"""
tests/test_accuracy.py — GoldenGate Retail AI accuracy regression tests (FIX 3).

GoldenGate's accuracy guarantees (COUNT(DISTINCT) for uniques, SUM÷SUM for
basket, no fabrication on empty periods) currently live only as *prompt
instructions* in agents/mallpulse/sub_agents.py. A model swap (Gemini 3 preview
→ GA, or a fallback to 2.5) could silently regress them.

These tests lock the ground truth against the live warehouse and, for each
trap, assert that the *correct* SQL semantics produce the right number while the
*naive/wrong* semantics produce the known-wrong number. If anyone "optimises"
a query into the wrong form, or the underlying data drifts, these fail.

They hit BigQuery directly (read-only) rather than driving the LLM agent —
that keeps them deterministic and CI-friendly. If BigQuery credentials are not
available the whole module is skipped rather than failing.

Ground truth re-verified 2026-06-03 against mallpulse-hackathon.goldengate_core
after the daily refresh completed May 2026 (warehouse now ends 2026-06-02):
  | unique customers, Stanford, May 2026 | 4,199  (naive SUM = 4,405) |
  | avg basket, Santana Row, May 2026    | $108.04                    |
  | distinct cities                      | 10                         |
  | revenue 2018 / 2031                  | no data (no fabrication)   |

NOTE: May 2026 is now a complete, frozen past month — daily incremental refreshes
only append June-onward, so these values are stable. A *full* warehouse rebuild
(REFRESH_MODE unset) regenerates history with a different RNG sequence and would
require re-baselining the two May figures below.

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

    def test_stanford_may_2026_count_distinct_is_4199(self):
        correct = _scalar(
            """
            SELECT COUNT(DISTINCT f.customer_id)
            FROM `mallpulse-hackathon.goldengate_core.fact_transactions` f
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%stanford%'
              AND f.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        )
        assert correct == 4199, f"expected 4199 unique customers, got {correct}"

    def test_naive_sum_of_aggregate_is_the_wrong_4405(self):
        """Documents the trap: SUM(unique_customers) double-counts across days.
        If this ever equals the COUNT(DISTINCT) value the trap has vanished and
        the assertion above no longer protects anything — so pin the wrong value.
        """
        wrong = _scalar(
            """
            SELECT SUM(a.unique_customers)
            FROM `mallpulse-hackathon.goldengate_core.agg_mall_daily` a
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%stanford%'
              AND a.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        )
        assert wrong == 4405
        assert wrong != 4199, "trap collapsed: naive sum now equals COUNT(DISTINCT)"


# ── Trap 2: average basket must be SUM÷SUM, not AVG(avg_basket) ────────────────

class TestAverageBasket:

    def test_santana_row_may_2026_sum_over_count_is_108_04(self):
        basket = _scalar(
            """
            SELECT ROUND(SUM(f.total_amount) / COUNT(DISTINCT f.invoice_no), 2)
            FROM `mallpulse-hackathon.goldengate_core.fact_transactions` f
            JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m USING (mall_id)
            WHERE LOWER(m.mall_name) LIKE '%santana%'
              AND f.date BETWEEN '2026-05-01' AND '2026-05-31'
            """
        )
        assert float(basket) == pytest.approx(108.04, abs=0.01)


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
