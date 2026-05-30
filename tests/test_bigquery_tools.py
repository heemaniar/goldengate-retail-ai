"""
tests/test_bigquery_tools.py — GoldenGate Retail AI

Rewritten for Bay Area malls and current function signatures.

Covers:
  - query_warehouse   (happy path, empty, NULLs, DML block, word-boundary, errors)
  - get_mall_summary  (happy path, unknown mall, period_days in SQL, BQ error)
  - get_top_tenants   (happy path, limit in SQL, period_days in SQL, empty, BQ error)
  - get_weather_traffic_correlation (happy path, empty, BQ error)
  - forecast_mall_revenue (happy path cache, days capped at 30, live fallback, BQ error)

Run:  pytest -v tests/test_bigquery_tools.py
"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_schema_fields(names: list[str]) -> list[MagicMock]:
    """Return mock BigQuery SchemaField objects with .name set."""
    fields = []
    for n in names:
        f = MagicMock()
        f.name = n
        fields.append(f)
    return fields


def _make_iterator(values_list: list[list], schema_names: list[str]) -> MagicMock:
    """Build a mock RowIterator.

    rows: each entry is a list of column values in schema order.
    The mock supports both iteration and .schema.
    """
    rows = []
    for vals in values_list:
        row = MagicMock()
        # query_warehouse iterates rows directly: `for row in rows`
        # and accesses values via positional iteration: `str(v) for v in row`
        row.__iter__ = MagicMock(return_value=iter(vals))
        rows.append(row)

    iterator = MagicMock()
    iterator.__iter__ = MagicMock(return_value=iter(rows))
    type(iterator).schema = PropertyMock(return_value=_make_schema_fields(schema_names))
    return iterator


def _patch_bq(values_list: list[list], schema_names: list[str]):
    """Patch _get_client so query().result() returns the specified rows."""
    mock_iter = _make_iterator(values_list, schema_names)
    mock_job = MagicMock()
    mock_job.result.return_value = mock_iter
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job
    return patch("tools.bigquery_tools._get_client", return_value=mock_client)


def _patch_bq_error(exc: Exception):
    """Patch _get_client so .query() raises the given exception."""
    mock_client = MagicMock()
    mock_client.query.side_effect = exc
    return patch("tools.bigquery_tools._get_client", return_value=mock_client)


# ── query_warehouse ───────────────────────────────────────────────────────────

class TestQueryWarehouse:

    def test_happy_path_returns_markdown_table(self):
        """SELECT → markdown table with headers and row data."""
        with _patch_bq([["Valley Fair", 1_500_000]], ["mall_name", "revenue_usd"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name, revenue_usd FROM agg_mall_daily")
        assert "| mall_name | revenue_usd |" in result
        assert "Valley Fair" in result
        assert "|" in result

    def test_empty_result_returns_no_rows_string(self):
        with _patch_bq([], ["mall_name"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name FROM dim_mall WHERE 1=0")
        assert "no rows" in result.lower()

    def test_null_values_render_as_empty_cell_not_none_string(self):
        """NULL column values must appear as empty string in markdown, not 'None'."""
        with _patch_bq([["Stanford Shopping Center", None]], ["mall_name", "revenue_usd"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name, revenue_usd FROM agg_mall_daily")
        assert "None" not in result
        # The cell should still be present but empty
        assert "Stanford Shopping Center" in result

    def test_blocks_insert_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("INSERT INTO dim_mall VALUES (1)")
        assert "Error" in result
        assert "INSERT" in result

    def test_blocks_update_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("UPDATE dim_mall SET city = 'X' WHERE 1=1")
        assert "Error" in result

    def test_blocks_delete_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("DELETE FROM dim_tenant WHERE 1=1")
        assert "Error" in result

    def test_blocks_drop_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("DROP TABLE goldengate_core.dim_tenant")
        assert "Error" in result

    def test_blocks_truncate_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("TRUNCATE TABLE goldengate_core.fact_transactions")
        assert "Error" in result

    def test_blocks_merge_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("MERGE target USING source ON (1=1)")
        assert "Error" in result

    def test_column_alias_with_drop_substring_not_blocked(self):
        """SELECT drop_count FROM t — 'drop' is a substring, not the keyword DROP.
        The word-boundary regex \bDROP\b must NOT block this valid SELECT.
        """
        with _patch_bq([[5]], ["drop_count"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT drop_count FROM agg_tenant_daily")
        assert "Error" not in result, (
            "BUG: column alias 'drop_count' should not trigger the DROP block. "
            "Ensure re.search uses \\bDROP\\b word boundaries."
        )

    def test_bigquery_api_error_returns_string_not_exception(self):
        """A BQ API error must be caught and returned as a string."""
        with _patch_bq_error(Exception("BQ service unavailable")):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT 1")
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_multiple_rows_all_appear(self):
        rows = [
            ["Valley Fair", 1_500_000],
            ["Stanford Shopping Center", 900_000],
            ["Santana Row", 700_000],
        ]
        schema = ["mall_name", "revenue_usd"]
        with _patch_bq(rows, schema):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name, revenue_usd FROM agg_mall_daily")
        assert "Valley Fair" in result
        assert "Stanford Shopping Center" in result
        assert "Santana Row" in result


# ── get_mall_summary ──────────────────────────────────────────────────────────

class TestGetMallSummary:

    def test_happy_path_returns_markdown(self):
        """get_mall_summary returns a markdown table for a known Bay Area mall."""
        row_vals = ["Valley Fair", "San Jose", "Premium Regional", 45_000_000, 99_000, 454.55]
        schema = ["mall_name", "city", "tier", "revenue_usd", "transactions", "avg_basket_usd"]
        with _patch_bq([row_vals], schema):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Valley Fair")
        assert "Valley Fair" in result
        assert "|" in result

    def test_unknown_mall_returns_no_rows(self):
        with _patch_bq([], ["mall_name"]):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Nonexistent Mall XYZ")
        assert "no rows" in result.lower()

    def test_period_days_flows_into_sql(self):
        """period_days=60 must appear as INTERVAL 60 DAY in the generated SQL."""
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n| --- |\n| val |\n"
            from tools.bigquery_tools import get_mall_summary
            get_mall_summary("Stanford Shopping Center", period_days=60)
        sql = mock_qw.call_args[0][0]
        assert "60" in sql

    def test_bigquery_error_returns_string(self):
        with _patch_bq_error(Exception("BQ unavailable")):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Santana Row")
        assert isinstance(result, str)
        assert "error" in result.lower()


# ── get_top_tenants ───────────────────────────────────────────────────────────

class TestGetTopTenants:

    def test_happy_path_returns_markdown(self):
        row_vals = ["Apple", "Electronics", "In-line", 2_500_000, 15_000, 166.67]
        schema = ["tenant_name", "category", "store_format",
                  "revenue_usd", "transactions", "avg_basket_usd"]
        with _patch_bq([row_vals], schema):
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Valley Fair")
        assert "Apple" in result
        assert "|" in result

    def test_limit_param_flows_into_sql(self):
        """limit=5 must appear as LIMIT 5 in the generated SQL."""
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n| --- |\n| val |\n"
            from tools.bigquery_tools import get_top_tenants
            get_top_tenants("Stanford Shopping Center", limit=5)
        sql = mock_qw.call_args[0][0]
        assert "5" in sql

    def test_period_days_flows_into_sql(self):
        """period_days=90 must appear in the generated SQL as INTERVAL 90 DAY."""
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n| --- |\n| val |\n"
            from tools.bigquery_tools import get_top_tenants
            get_top_tenants("Santana Row", period_days=90)
        sql = mock_qw.call_args[0][0]
        assert "90" in sql

    def test_empty_result_returns_no_rows(self):
        with _patch_bq([], ["tenant_name"]):
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Valley Fair")
        assert "no rows" in result.lower()

    def test_bigquery_error_returns_string(self):
        with _patch_bq_error(Exception("BQ unavailable")):
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Stanford Shopping Center")
        assert isinstance(result, str)
        assert "error" in result.lower()


# ── get_weather_traffic_correlation ──────────────────────────────────────────

class TestGetWeatherTrafficCorrelation:

    def test_happy_path_returns_markdown(self):
        row_vals = ["Clear / Dry", 45, 12000, 18.5]
        schema = ["weather_condition", "days", "avg_daily_visits", "avg_temp_c"]
        with _patch_bq([row_vals], schema):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Santana Row")
        assert "|" in result
        assert "Clear / Dry" in result

    def test_empty_result_returns_no_rows(self):
        with _patch_bq([], ["weather_condition"]):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Valley Fair")
        assert "no rows" in result.lower()

    def test_bigquery_error_returns_string(self):
        with _patch_bq_error(Exception("BQ unavailable")):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Stanford Shopping Center")
        assert isinstance(result, str)
        assert "error" in result.lower()


# ── forecast_mall_revenue ─────────────────────────────────────────────────────

class TestForecastMallRevenue:

    def _cache_hit_mock(self) -> MagicMock:
        """Cache query returns rows → forecast is served from cache."""
        row_vals = ["Valley Fair", "2026-06-01", 95_000, 80_000, 110_000]
        schema = ["mall_name", "forecast_date", "forecast_revenue_usd",
                  "lower_90_usd", "upper_90_usd"]
        mock_iter = _make_iterator([row_vals], schema)
        mock_job = MagicMock()
        mock_job.result.return_value = mock_iter
        mock_client = MagicMock()
        mock_client.query.return_value = mock_job
        return mock_client

    def _cache_miss_mock(self) -> MagicMock:
        """Cache query returns no rows → falls through to live ML.FORECAST."""
        # First query (cache): empty
        empty_iter = _make_iterator([], [])
        cache_job = MagicMock()
        cache_job.result.return_value = empty_iter

        # Second query (live ML.FORECAST): returns data
        row_vals = ["Valley Fair", "2026-06-01", 95_000, 80_000, 110_000]
        schema = ["mall_name", "forecast_date", "forecast_revenue_usd",
                  "lower_90_usd", "upper_90_usd"]
        live_iter = _make_iterator([row_vals], schema)
        live_job = MagicMock()
        live_job.result.return_value = live_iter

        mock_client = MagicMock()
        mock_client.query.side_effect = [cache_job, live_job]
        return mock_client

    def test_happy_path_cache_hit_returns_markdown(self):
        """When forecast_cache has today's rows the function returns them as markdown."""
        mock_client = self._cache_hit_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Valley Fair", days=30)
        assert "|" in result
        assert "Valley Fair" in result

    def test_days_capped_at_30(self):
        """days > 30 must be silently clamped to 30 (the function cap)."""
        mock_client = self._cache_hit_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            forecast_mall_revenue("Valley Fair", days=999)
        sql_called = mock_client.query.call_args_list[0][0][0]
        # The capped value 30 must appear in the SQL; 999 must not
        assert "999" not in sql_called
        assert "30" in sql_called

    def test_cache_miss_falls_back_to_live_ml_forecast(self):
        """When cache is empty the function calls ML.FORECAST and returns markdown."""
        mock_client = self._cache_miss_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Stanford Shopping Center", days=14)
        # Two queries should have been issued: cache check, then live
        assert mock_client.query.call_count == 2
        assert isinstance(result, str)

    def test_bigquery_error_returns_string(self):
        """A BQ error in the cache query must return an error string, not raise."""
        with _patch_bq_error(Exception("BQ service unavailable")):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Santana Row")
        assert isinstance(result, str)
        assert "error" in result.lower()
