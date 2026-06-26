#!/usr/bin/env bash
# Unattended weekend batch: convert the whole Dungeon Masters Guild tree to
# 5etools JSON across both Spark endpoints, document-boundary load-balanced.
#
# Resumable: re-running picks up where it left off (skips finished <stem>.json,
# resumes partial docs from cached chunk responses, retries failures).
#
#   ./convert_dmsguild.sh --list     # scan + classify + plan, convert nothing
#   ./convert_dmsguild.sh            # run in the foreground
#   nohup ./convert_dmsguild.sh > dmsguild-batch.out 2>&1 &   # survive logout
#
# Both boxes are equal 40K-input endpoints; work round-robins across them and
# every prompt chunk is capped (PDF2E_MAX_CHUNK_CHARS) so nothing overflows. It
# starts on whichever box is reachable and auto-joins the others when they come up.
#
# -u keeps stdout unbuffered so dmsguild-batch.out streams in real time (tail -f).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -u batch_convert.py "$@"
