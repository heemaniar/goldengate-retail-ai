"""
Quick smoke test — sends 10 different questions through the ADK multi-agent
pipeline and prints pass/fail. Run from project root:

    .venv/bin/python tests/run_agent_questions.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.mallpulse.agent import root_agent

QUESTIONS = [
    # data_unifier → query_warehouse
    ("Revenue count",     "How many transactions did Valley Fair have in March 2024?"),
    # data_unifier → get_mall_summary
    ("Mall summary",      "Give me a summary of Stanford Shopping Center's overall revenue performance"),
    # data_unifier → get_weather_traffic_correlation
    ("Weather impact",    "What was the weather impact on foot traffic at Santana Row in 2024?"),
    # data_unifier → portfolio query
    ("Portfolio compare", "Which of the 13 Bay Area malls had the highest total revenue in 2024?"),
    # tenant_diagnoser → get_top_tenants
    ("Top tenants",       "Who are the top 5 tenants at Stanford Shopping Center by revenue?"),
    # tenant_diagnoser → lease query
    ("Lease expiry",      "Which tenants have leases expiring in the next 6 months?"),
    # tenant_diagnoser → cross-mall brand
    ("Cross-mall brand",  "How does lululemon perform across all Bay Area malls? Compare revenue."),
    # action_recommender → forecast
    ("Forecast",          "Forecast revenue for Valley Fair for the next 30 days"),
    # action_recommender → recommendations
    ("Actions",           "What are the top 3 actions I should take this week at Valley Fair?"),
    # data_unifier → demographics
    ("Demographics",      "What is the customer age breakdown at Great Mall?"),
]

GREEN = "\033[32m"
RED   = "\033[31m"
RESET = "\033[0m"


async def main():
    svc     = InMemorySessionService()
    session = await svc.create_session(app_name="goldengate", user_id="test")
    runner  = Runner(agent=root_agent, app_name="goldengate", session_service=svc)

    passed = failed = 0
    for label, question in QUESTIONS:
        # Fresh session per question so they don't bleed context
        session = await svc.create_session(app_name="goldengate", user_id="test")
        print(f"\n{'='*60}")
        print(f"[{label}] {question}")
        try:
            answer = ""
            for event in runner.run(
                user_id="test",
                session_id=session.id,
                new_message=Content(parts=[Part(text=question)], role="user"),
            ):
                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if part.text:
                            answer += part.text

            if answer and len(answer) > 20:
                print(f"{GREEN}PASS{RESET} — {len(answer)} chars")
                print(answer[:300].replace("\n", " ") + ("…" if len(answer) > 300 else ""))
                passed += 1
            else:
                print(f"{RED}FAIL{RESET} — empty/short response: {repr(answer[:100])}")
                failed += 1
        except Exception as e:
            print(f"{RED}ERROR{RESET} — {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(QUESTIONS)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
