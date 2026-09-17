#!/usr/bin/env bash
# Runs the full backend test suite plus the evaluation harness.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/backend"
echo "== Unit tests =="
pytest tests/unit -v
echo "== Integration tests =="
pytest tests/integration -v
echo "== Full suite with coverage =="
pytest --cov=app --cov-report=term-missing
echo "== Evaluation harness =="
python -m tests.evaluation.run_evaluation
