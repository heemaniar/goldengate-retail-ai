"""
tests/test_agents.py — GoldenGate Retail AI agent structure tests.

Verifies that agent modules import cleanly, that the root agent and
sub-agents have the expected names/tools, and that McpToolset is wired
into the data_unifier.

No real BigQuery or Fivetran calls are made — all external services are
patched at import time.

Run:  pytest -v tests/test_agents.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Patch heavy external dependencies BEFORE any agent module is imported.
# This prevents real BQ clients, MCP subprocesses, and Phoenix tracers from
# being created during the test run.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure project root is on sys.path (pytest.ini sets pythonpath=. but be safe)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture(autouse=True, scope="module")
def _patch_external():
    """
    Module-scoped autouse fixture that patches all external I/O before the
    agent modules are imported.

    We use plain unittest.mock.patch as context managers so they stay active
    for the entire module.
    """
    patches = [
        patch("google.cloud.bigquery.Client"),
        # Prevent McpToolset from actually spawning a subprocess
        patch(
            "google.adk.tools.mcp_tool.mcp_toolset.McpToolset.__init__",
            return_value=None,
        ),
    ]
    started = [p.start() for p in patches]
    yield started
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Import agent modules (done inside test functions to respect the fixture)
# ---------------------------------------------------------------------------


class TestSubAgentsImport:

    def test_sub_agents_module_imports_without_error(self):
        """agents/mallpulse/sub_agents.py must be importable."""
        import importlib
        mod = importlib.import_module("agents.mallpulse.sub_agents")
        assert mod is not None

    def test_agent_module_imports_without_error(self):
        """agents/mallpulse/agent.py must be importable."""
        import importlib
        mod = importlib.import_module("agents.mallpulse.agent")
        assert mod is not None


class TestRootAgent:

    def test_root_agent_exists(self):
        from agents.mallpulse.agent import root_agent
        assert root_agent is not None

    def test_root_agent_name_is_goldengate(self):
        from agents.mallpulse.agent import root_agent
        assert root_agent.name == "goldengate"

    def test_root_agent_has_three_tools(self):
        """Root agent should have exactly 3 AgentTool wrappers."""
        from agents.mallpulse.agent import root_agent
        assert len(root_agent.tools) == 3

    def test_root_agent_instruction_contains_today_date(self):
        """Instruction must contain a date anchor, not a stale placeholder."""
        from agents.mallpulse.agent import root_agent
        assert "2026" in root_agent.instruction or "TODAY" in root_agent.instruction


class TestSubAgents:

    def test_data_unifier_is_agent_instance(self):
        from google.adk.agents import Agent
        from agents.mallpulse.sub_agents import data_unifier
        assert isinstance(data_unifier, Agent)

    def test_data_unifier_name(self):
        from agents.mallpulse.sub_agents import data_unifier
        assert data_unifier.name == "data_unifier"

    def test_tenant_diagnoser_is_agent_instance(self):
        from google.adk.agents import Agent
        from agents.mallpulse.sub_agents import tenant_diagnoser
        assert isinstance(tenant_diagnoser, Agent)

    def test_tenant_diagnoser_name(self):
        from agents.mallpulse.sub_agents import tenant_diagnoser
        assert tenant_diagnoser.name == "tenant_diagnoser"

    def test_action_recommender_is_agent_instance(self):
        from google.adk.agents import Agent
        from agents.mallpulse.sub_agents import action_recommender
        assert isinstance(action_recommender, Agent)

    def test_action_recommender_name(self):
        from agents.mallpulse.sub_agents import action_recommender
        assert action_recommender.name == "action_recommender"


class TestSubAgentTools:

    def _tool_names(self, agent) -> list[str]:
        """Return the list of callable tool names for an agent."""
        names = []
        for t in agent.tools:
            if callable(t) and hasattr(t, "__name__"):
                names.append(t.__name__)
            elif hasattr(t, "name"):
                names.append(t.name)
            elif hasattr(t, "__class__"):
                names.append(type(t).__name__)
        return names

    def test_data_unifier_has_query_warehouse(self):
        from agents.mallpulse.sub_agents import data_unifier
        names = self._tool_names(data_unifier)
        assert "query_warehouse" in names

    def test_data_unifier_has_get_mall_summary(self):
        from agents.mallpulse.sub_agents import data_unifier
        names = self._tool_names(data_unifier)
        assert "get_mall_summary" in names

    def test_data_unifier_has_get_weather_traffic_correlation(self):
        from agents.mallpulse.sub_agents import data_unifier
        names = self._tool_names(data_unifier)
        assert "get_weather_traffic_correlation" in names

    def test_data_unifier_has_mcp_toolset(self):
        """McpToolset (Fivetran) must be present in data_unifier's tools list."""
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
        from agents.mallpulse.sub_agents import data_unifier
        mcp_tools = [t for t in data_unifier.tools if isinstance(t, McpToolset)]
        assert len(mcp_tools) >= 1, "data_unifier should have at least one McpToolset"

    def test_tenant_diagnoser_has_query_warehouse(self):
        from agents.mallpulse.sub_agents import tenant_diagnoser
        names = self._tool_names(tenant_diagnoser)
        assert "query_warehouse" in names

    def test_tenant_diagnoser_has_get_top_tenants(self):
        from agents.mallpulse.sub_agents import tenant_diagnoser
        names = self._tool_names(tenant_diagnoser)
        assert "get_top_tenants" in names

    def test_action_recommender_has_forecast_mall_revenue(self):
        from agents.mallpulse.sub_agents import action_recommender
        names = self._tool_names(action_recommender)
        assert "forecast_mall_revenue" in names

    def test_action_recommender_has_query_warehouse(self):
        from agents.mallpulse.sub_agents import action_recommender
        names = self._tool_names(action_recommender)
        assert "query_warehouse" in names

    def test_action_recommender_has_get_top_tenants(self):
        from agents.mallpulse.sub_agents import action_recommender
        names = self._tool_names(action_recommender)
        assert "get_top_tenants" in names
