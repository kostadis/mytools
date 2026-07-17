#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
env_file="$root/.env"

if [[ ! -f "$env_file" ]]; then
  echo "error: $env_file not found. Copy .env.example to .env and fill in ANTHROPIC_API_KEY." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "error: ANTHROPIC_API_KEY not set in $env_file" >&2
  exit 1
fi

exec python3 "$root/converters/pdf_to_5etools_v2.py" "$@"
