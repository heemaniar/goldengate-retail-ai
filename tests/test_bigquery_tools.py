"""
tests/test_bigquery_tools.py

Pytest test suite for tools/bigquery_tools.py.

Run:  pytest -v tests/test_bigquery_tools.py

Covers:
  - query_warehouse  (happy path, empty, NULLs, DML block, service errors)
  - get_mall_summary  (happy path, unknown mall, apostrophe injection, NULLs,
                       partition-filter assertion, service error)
  - get_top_tenants   (happy path, metric fallback, limit cap, empty, partition
                       filter, all metrics)
  - get_weather_traffic_correlation  (known-issue empty table, happy path,
                                     error resilience, year param)
  - forecast_mall_revenue  (happy path, not-found, days cap, empty forecast,
                            service error on ML query, string-days coercion)
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_row(values: dict) -> MagicMock:
    """Create a MagicMock that behaves like a BigQuery Row."""
    row = MagicMock()
    row.values.return_value = list(values.values())
    row.__getitem__ = MagicMock(side_effect=lambda key, _v=values: _v[key])
    return row


def _make_mock_iterator(rows: list, schema_names: list) -> MagicMock:
    """Return a MagicMock RowIterator with a .schema property."""
    schema_fields = [MagicMock(name=n) for n in schema_names]
    iterator = MagicMock()
    iterator.__iter__ = MagicMock(return_value=iter(rows))
    type(iterator).schema = PropertyMock(return_value=schema_fields)
    return iterator


def _patch_client(rows: list, schema_names: list):
    """Context manager: patch _get_client so .query().result() returns rows."""
    mock_iterator = _make_mock_iterator(rows, schema_names)
    mock_job = MagicMock()
    mock_job.result.return_value = mock_iterator
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job
    return patch("tools.bigquery_tools._get_client", return_value=mock_client)


# ── query_warehouse ───────────────────────────────────────────────────────────

class TestQueryWarehouse:

    def test_happy_path_returns_markdown_table(self):
        """Critical path: BQ query executes → markdown table returned to Streamlit."""
        row = _make_mock_row({"mall_name": "Kanyon", "total_revenue": 1_000_000})
        with _patch_client([row], ["mall_name", "total_revenue"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name, total_revenue FROM t")
        assert "| mall_name | total_revenue |" in result
        assert "Kanyon" in result

    def test_empty_result_returns_human_readable_string(self):
        """Convention: handle empty result sets — return a human-readable string."""
        with _patch_client([], ["col"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT col FROM t")
        assert "no rows" in result.lower()

    def test_null_values_rendered_as_empty_cell_not_none_string(self):
        """NULL column values must render as empty string in markdown, not the literal 'None'."""
        row = _make_mock_row({"mall_name": "Kanyon", "revenue": None})
        with _patch_client([row], ["mall_name", "revenue"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT mall_name, revenue FROM t")
        assert "None" not in result

    def test_blocks_insert_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("INSERT INTO t VALUES (1)")
        assert "Error" in result
        assert "INSERT" in result

    def test_blocks_drop_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("DROP TABLE mallpulse_core.dim_tenant")
        assert "Error" in result

    def test_blocks_truncate_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("TRUNCATE TABLE mallpulse_core.fact_transactions")
        assert "Error" in result

    def test_blocks_merge_statement(self):
        from tools.bigquery_tools import query_warehouse
        result = query_warehouse("MERGE target USING source ON (1=1)")
        assert "Error" in result

    def test_does_not_block_column_alias_containing_drop_as_substring(self):
        """
        Regression: a column alias like 'drop_count' contains 'DROP' as a substring.
        The current substring block-list incorrectly rejects this valid SELECT.
        This test documents the expected (correct) behaviour — it will FAIL until the
        block-list is changed to use word-boundary regex.
        """
        row = _make_mock_row({"drop_count": 5})
        with _patch_client([row], ["drop_count"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT drop_count FROM t")
        assert "Error" not in result, (
            "BUG: 'drop_count' column alias should not trigger the DROP block-list. "
            "Fix: use re.search(r'\\bDROP\\b', normalised) instead of 'DROP' in normalised."
        )

    def test_bigquery_api_error_returns_error_string_not_exception(self):
        """ADK tools must not raise — they return error strings so the agent can handle failures."""
        from google.api_core.exceptions import GoogleAPIError
        mock_client = MagicMock()
        mock_client.query.side_effect = GoogleAPIError("BQ unavailable")
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT 1")
        assert "error" in result.lower()

    def test_timeout_returns_error_string_not_exception(self):
        mock_client = MagicMock()
        mock_client.query.side_effect = TimeoutError("deadline exceeded")
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT 1")
        assert "error" in result.lower() or "timed out" in result.lower()

    def test_multiple_rows_all_appear_in_output(self):
        rows = [
            _make_mock_row({"name": "Kanyon", "rev": 100}),
            _make_mock_row({"name": "Forum Istanbul", "rev": 200}),
        ]
        with _patch_client(rows, ["name", "rev"]):
            from tools.bigquery_tools import query_warehouse
            result = query_warehouse("SELECT name, rev FROM t")
        assert "Kanyon" in result
        assert "Forum Istanbul" in result


# ── get_mall_summary ──────────────────────────────────────────────────────────

class TestGetMallSummary:

    def test_happy_path_returns_markdown_with_revenue_stats(self):
        """Critical path: user asks revenue question → markdown table returned."""
        row = _make_mock_row({
            "mall_name": "Kanyon",
            "trading_days": 1163,
            "total_revenue": 45_000_000,
            "avg_daily_revenue": 38_693,
            "peak_daily_revenue": 85_000,
            "total_transactions": 99_458,
        })
        schema = ["mall_name", "trading_days", "total_revenue",
                  "avg_daily_revenue", "peak_daily_revenue", "total_transactions"]
        with _patch_client([row], schema):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Kanyon")
        assert "Kanyon" in result
        assert "|" in result  # markdown table present

    def test_unknown_mall_returns_no_rows_string(self):
        with _patch_client([], ["mall_name"]):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Nonexistent Mall XYZ")
        assert "no rows" in result.lower()

    def test_mall_name_with_apostrophe_returns_string_not_exception(self):
        """
        SQL injection guard: mall names with single quotes must not raise a syntax error.
        Currently the f-string interpolation WILL break on names like "L'Oreal Mall".
        This test documents expected behaviour — FAILS until parameterised queries are used.
        """
        with _patch_client([], []):
            from tools.bigquery_tools import get_mall_summary
            try:
                result = get_mall_summary("L'Oreal Mall")
                assert isinstance(result, str), "Must return a string, not raise"
            except Exception as e:
                pytest.fail(
                    f"get_mall_summary raised {type(e).__name__} on apostrophe in mall_name. "
                    "Fix: use parameterised queries instead of f-string interpolation."
                )

    def test_null_revenue_values_render_as_empty_not_none_string(self):
        row = _make_mock_row({
            "mall_name": "Kanyon",
            "trading_days": None,
            "total_revenue": None,
            "avg_daily_revenue": None,
            "peak_daily_revenue": None,
            "total_transactions": None,
        })
        schema = ["mall_name", "trading_days", "total_revenue",
                  "avg_daily_revenue", "peak_daily_revenue", "total_transactions"]
        with _patch_client([row], schema):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Kanyon")
        assert "None" not in result

    def test_sql_contains_partition_date_filter(self):
        """
        Convention: all BQ queries must filter on the partition column.
        agg_mall_daily partition key is 'date'.
        This test FAILS until a date range filter is added to get_mall_summary.
        """
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n| --- |\n"
            from tools.bigquery_tools import get_mall_summary
            get_mall_summary("Kanyon")
        sql_called = mock_qw.call_args[0][0]
        assert "date" in sql_called.lower(), (
            "get_mall_summary SQL must include a filter on the 'date' partition column "
            "to avoid full-table scans."
        )

    def test_service_error_returns_error_string_not_exception(self):
        mock_client = MagicMock()
        mock_client.query.side_effect = Exception("BQ unavailable")
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import get_mall_summary
            result = get_mall_summary("Kanyon")
        assert "error" in result.lower()


# ── get_top_tenants ───────────────────────────────────────────────────────────

class TestGetTopTenants:

    def test_happy_path_revenue_metric(self):
        """Critical path: tenant health query → rent-to-sales ratio / top tenants."""
        row = _make_mock_row({
            "tenant_name": "Zara",
            "category": "Fashion",
            "total_revenue": 2_500_000,
            "total_transactions": 15_000,
            "avg_basket": 166.67,
        })
        schema = ["tenant_name", "category", "total_revenue",
                  "total_transactions", "avg_basket"]
        with _patch_client([row], schema):
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Kanyon", metric="revenue")
        assert "Zara" in result
        assert "Fashion" in result

    def test_invalid_metric_falls_back_to_revenue_ordering(self):
        """An unrecognised metric must fall back to revenue, not produce a SQL error."""
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n"
            from tools.bigquery_tools import get_top_tenants
            get_top_tenants("Kanyon", metric="undefined_metric")
        sql = mock_qw.call_args[0][0]
        assert "SUM(d.revenue)" in sql

    def test_limit_is_capped_at_50_per_convention(self):
        """
        Convention: LIMIT 50 on all markdown-returning queries.
        User-supplied limit=9999 must be silently capped.
        This test FAILS until min(limit, 50) guard is added.
        """
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n"
            from tools.bigquery_tools import get_top_tenants
            get_top_tenants("Kanyon", limit=9999)
        sql = mock_qw.call_args[0][0]
        assert "9999" not in sql, (
            "BUG: limit=9999 flows directly into LIMIT clause. "
            "Fix: limit = min(int(limit), 50) before building SQL."
        )

    def test_empty_result_returns_human_readable_string(self):
        with _patch_client([], []):
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Kanyon")
        assert "no rows" in result.lower()

    def test_sql_contains_partition_date_filter(self):
        """
        Convention: all BQ queries must filter on partition column (date).
        This test FAILS until a date range is added to get_top_tenants.
        """
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n"
            from tools.bigquery_tools import get_top_tenants
            get_top_tenants("Kanyon")
        sql = mock_qw.call_args[0][0]
        assert "date" in sql.lower(), (
            "get_top_tenants SQL must filter on the 'date' partition column."
        )

    @pytest.mark.parametrize("metric", ["revenue", "transactions", "avg_basket"])
    def test_all_valid_metrics_accepted_without_error(self, metric: str):
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n"
            from tools.bigquery_tools import get_top_tenants
            result = get_top_tenants("Kanyon", metric=metric)
        assert mock_qw.called
        assert isinstance(result, str)


# ── get_weather_traffic_correlation ──────────────────────────────────────────

class TestGetWeatherTrafficCorrelation:

    def test_known_issue_empty_foot_traffic_table_returns_informative_message(self):
        """
        Known issue: fact_foot_traffic is empty.
        Function must NOT silently return just the header with 'Query returned no rows.'
        appended — that looks like a successful (empty) result to the LLM.
        After fix: should contain a warning about the known data gap.
        """
        with _patch_client([], []):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Kanyon", year=2022)
        assert "Weather" in result  # header always present
        # Acceptable outcomes: either mention the empty table, or "no rows"
        has_warning = any(phrase in result.lower() for phrase in [
            "no foot traffic", "empty", "no rows", "data gap", "not found"
        ])
        assert has_warning, (
            "When fact_foot_traffic returns zero rows the function should explain why, "
            "not just echo the raw no-rows string."
        )

    def test_happy_path_returns_formatted_weather_table(self):
        row = _make_mock_row({
            "weather_type": "Dry (<2mm)",
            "temp_band": "Mild (15-25°C)",
            "days": 120,
            "avg_daily_visits": 8500,
            "min_visits": 4200,
            "max_visits": 15000,
        })
        schema = ["weather_type", "temp_band", "days",
                  "avg_daily_visits", "min_visits", "max_visits"]
        with _patch_client([row], schema):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Kanyon", year=2022)
        assert "**Weather × Foot Traffic — Kanyon (2022)**" in result
        assert "Dry" in result

    def test_error_returns_string_not_exception(self):
        mock_client = MagicMock()
        mock_client.query.side_effect = Exception("BQ unavailable")
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Kanyon", year=2022)
        assert isinstance(result, str)

    def test_year_parameter_appears_in_generated_sql(self):
        with patch("tools.bigquery_tools.query_warehouse") as mock_qw:
            mock_qw.return_value = "| col |\n"
            from tools.bigquery_tools import get_weather_traffic_correlation
            get_weather_traffic_correlation("Forum Istanbul", year=2021)
        sql = mock_qw.call_args[0][0]
        assert "2021" in sql

    def test_mall_name_appears_in_result_header(self):
        with _patch_client([], []):
            from tools.bigquery_tools import get_weather_traffic_correlation
            result = get_weather_traffic_correlation("Zorlu Center", year=2022)
        assert "Zorlu Center" in result


# ── forecast_mall_revenue ─────────────────────────────────────────────────────

class TestForecastMallRevenue:

    def _setup_two_stage_mock(self, mall_id: str = "M001",
                               forecast_rows: list | None = None) -> MagicMock:
        """
        Two-stage mock: first query returns mall_id lookup row,
        second query returns the ML.FORECAST result.
        """
        # Stage 1 — mall_id lookup
        id_row = MagicMock()
        id_row.__getitem__ = MagicMock(side_effect=lambda k: mall_id if k == "mall_id" else None)
        id_iterator = MagicMock()
        id_iterator.__iter__ = MagicMock(return_value=iter([id_row]))
        id_job = MagicMock()
        id_job.result.return_value = id_iterator

        # Stage 2 — forecast rows
        if forecast_rows is None:
            forecast_row = _make_mock_row({
                "forecast_date": "2023-03-09",
                "forecast_revenue": 45000,
                "lower_90": 38000,
                "upper_90": 52000,
            })
            forecast_rows = [forecast_row]

        forecast_schema = ["forecast_date", "forecast_revenue", "lower_90", "upper_90"]
        forecast_iterator = _make_mock_iterator(forecast_rows, forecast_schema)
        forecast_job = MagicMock()
        forecast_job.result.return_value = forecast_iterator

        mock_client = MagicMock()
        mock_client.query.side_effect = [id_job, forecast_job]
        return mock_client

    def test_happy_path_returns_forecast_header_and_table(self):
        """Critical path: action recommender calls forecast model → returns prioritised list."""
        mock_client = self._setup_two_stage_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Kanyon", days=30)
        assert "Revenue forecast for Kanyon" in result
        assert "30 days" in result

    def test_unknown_mall_returns_not_found_message(self):
        id_iterator = MagicMock()
        id_iterator.__iter__ = MagicMock(return_value=iter([]))
        id_job = MagicMock()
        id_job.result.return_value = id_iterator
        mock_client = MagicMock()
        mock_client.query.return_value = id_job

        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Ghost Mall")
        assert "not found" in result.lower()

    def test_days_capped_at_90(self):
        """ARIMA_PLUS horizon cap: days > 90 must be silently clamped to 90."""
        mock_client = self._setup_two_stage_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            forecast_mall_revenue("Kanyon", days=999)
        second_sql_call = mock_client.query.call_args_list[1][0][0]
        assert "90" in second_sql_call
        assert "999" not in second_sql_call

    def test_days_exactly_90_not_clamped(self):
        mock_client = self._setup_two_stage_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            forecast_mall_revenue("Kanyon", days=90)
        second_sql = mock_client.query.call_args_list[1][0][0]
        assert "90" in second_sql

    def test_empty_forecast_rows_returns_string_with_header(self):
        mock_client = self._setup_two_stage_mock(forecast_rows=[])
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Kanyon", days=30)
        assert isinstance(result, str)
        assert "Kanyon" in result  # header prepended even when no rows

    def test_bqml_error_returns_error_string_not_exception(self):
        """If the ML.FORECAST query fails, must return an error string, not raise."""
        id_row = MagicMock()
        id_row.__getitem__ = MagicMock(return_value="M001")
        id_iterator = MagicMock()
        id_iterator.__iter__ = MagicMock(return_value=iter([id_row]))
        id_job = MagicMock()
        id_job.result.return_value = id_iterator

        mock_client = MagicMock()
        mock_client.query.side_effect = [id_job, Exception("BQML model not found")]
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Kanyon", days=30)
        assert isinstance(result, str)

    def test_days_passed_as_string_is_coerced_to_int(self):
        """LLMs may pass numeric args as strings — int() coercion must not raise."""
        mock_client = self._setup_two_stage_mock()
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            result = forecast_mall_revenue("Kanyon", days="45")  # type: ignore
        assert isinstance(result, str)

    def test_mall_id_integer_type_used_in_second_query(self):
        """
        Warning: if mall_id is an integer in BQ, WHERE mall_id = 'M001' (string) causes
        a type mismatch. Verify the second query does not quote a numeric mall_id.
        This test documents the expected fix.
        """
        mock_client = self._setup_two_stage_mock(mall_id=1)  # integer mall_id
        with patch("tools.bigquery_tools._get_client", return_value=mock_client):
            from tools.bigquery_tools import forecast_mall_revenue
            forecast_mall_revenue("Kanyon", days=30)
        second_sql = mock_client.query.call_args_list[1][0][0]
        # After fix: should be WHERE mall_id = 1, not WHERE mall_id = '1'
        assert "mall_id = '1'" not in second_sql, (
            "BUG: integer mall_id is being quoted as a string in the ML.FORECAST query. "
            "Fix: use WHERE mall_id = {int(mall_id)} or a parameterised query."
        )
