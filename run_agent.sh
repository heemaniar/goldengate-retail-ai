#!/bin/bash
# MallPulse — start the ADK web UI locally
# Usage: ./run_agent.sh
# Then open: http://127.0.0.1:8000

set -e
cd "$(dirname "$0")"

source .venv/bin/activate

export GOOGLE_GENAI_USE_VERTEXAI=1
export GOOGLE_CLOUD_PROJECT=mallpulse-hackathon
export GOOGLE_CLOUD_LOCATION=us-central1

echo ""
echo "Starting MallPulse agent..."
echo "Open: http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."
echo ""

adk web agents/
