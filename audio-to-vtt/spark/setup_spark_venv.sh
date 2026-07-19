#!/usr/bin/env bash
#
# setup_spark_venv.sh -- one-time bootstrap for faster-whisper on the DGX Spark.
#
# Run ON the Spark box (after scp'ing this script over), not on the workstation:
#   scp spark/setup_spark_venv.sh spark2:~/
#   ssh spark2 'bash ~/setup_spark_venv.sh'
#
# ctranslate2's default PyPI wheel for linux_aarch64 is CPU-only. The NVIDIA
# package index carries aarch64+CUDA builds instead -- this is a
# DGX-Spark-specific gotcha (see speaches-ai/speaches#620). Installing
# ctranslate2 explicitly from that index BEFORE faster-whisper (which would
# otherwise pull the default PyPI wheel as a transitive dependency) avoids
# silently degrading to CPU.
set -euo pipefail

VENV_DIR="${1:-$HOME/.venvs/audio-to-vtt}"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install --extra-index-url https://pypi.nvidia.com ctranslate2
pip install faster-whisper

echo "--- ctranslate2 / faster-whisper installed ---"
python3 -c "import ctranslate2; print('ctranslate2', ctranslate2.__version__)"
python3 -c "import faster_whisper; print('faster-whisper', faster_whisper.__version__)"

echo ""
echo "Real GPU-vs-CPU verification is NOT a static check here -- it is done"
echo "empirically via retranscribe.py --smoke-test, which loads an actual model"
echo "and reports device_used from the live load attempt. See audio-to-vtt/CLAUDE.md."
