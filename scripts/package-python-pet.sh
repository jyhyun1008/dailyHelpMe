#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" != "--no-build" ]]; then bash scripts/build-python-pet.sh; fi
.venv-pet/bin/python scripts/package-release.py
