#!/bin/bash
# Start the Prompt Editor web app

set -e

# Ensure web dependencies are installed
uv pip install fastapi 'uvicorn[standard]' 2>/dev/null || true

# Start the server (port configurable as first arg, default 8420)
uv run uvicorn debate.prompt_editor.server:app --host 0.0.0.0 --port "${1:-8420}" --reload
