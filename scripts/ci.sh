#!/usr/bin/env bash
set -euo pipefail

poetry run ruff check .
poetry run black --check .
poetry run mypy .
poetry run pytest
