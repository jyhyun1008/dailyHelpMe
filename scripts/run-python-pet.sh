#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv-pet/bin/python ]]; then
  PET_PYTHON="${DOA_PYTHON:-}"
  if [[ -z "$PET_PYTHON" ]]; then
    for candidate in /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
        PET_PYTHON="$candidate"
        break
      fi
    done
  fi
  if [[ -z "$PET_PYTHON" ]]; then
    echo 'Python 3.10 이상을 설치해주세요. DOA_PYTHON으로 실행 경로를 지정할 수도 있어요.' >&2
    exit 1
  fi
  "$PET_PYTHON" -m venv .venv-pet
fi
if ! .venv-pet/bin/python -c 'import PySide6, pywebpush' >/dev/null 2>&1; then
  .venv-pet/bin/python -m pip install -r desktop/python/requirements.txt
fi
exec .venv-pet/bin/python desktop/python/app.py
