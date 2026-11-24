#!/usr/bin/env python3
"""Build and atomically install the optional Linux parser for this checkout."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MODULE = "fa_converters_pdf_to_5etools_v2_py_parse_markdown_headings"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="use cached Cargo dependencies")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("this optional build helper currently supports Linux")
    crate = Path(__file__).resolve().parent
    command = ["cargo", "build", "--release", "--locked", "--manifest-path",
               str(crate / "Cargo.toml"), "--target-dir", str(crate / "target")]
    if args.offline:
        command.append("--offline")
    subprocess.run(command, env={**os.environ, "PYO3_PYTHON": sys.executable}, check=True)
    output = crate / "target" / "python"
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{MODULE}.abi3.so"
    with tempfile.NamedTemporaryFile(dir=output, delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        shutil.copy2(crate / "target" / "release" / f"lib{MODULE}.so", staging)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)
    print(f"Installed {destination}")


if __name__ == "__main__":
    main()
