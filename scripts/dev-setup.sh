#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --extra dev --reinstall-package mirror-claude-coach
uv run python -c "import mirror; print('mirror import ok:', mirror.__file__)"
