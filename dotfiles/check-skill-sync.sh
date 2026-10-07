#!/usr/bin/env bash
# Compatibility entry point used by CI and existing local workflows.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$here/check-skill-layout.py" --dotfiles "$here"
