#!/usr/bin/env python3
"""Check that the source deployed on GenLayer matches contracts/bounty_court.py.

The steward asked for matching submitted and deployed source. This prints one
digest for each side and exits non-zero when they differ, so the check is a
command, not a claim.

    python scripts/verify_deployed_source.py 0x47344B9269e0c2c1E7cDCF77C7df01219b0c77A2

Normalisation: the CLI returns the source with CRLF line endings and trailing
blank lines that are not part of the file. Both sides are compared after
converting CRLF to LF and stripping trailing whitespace.
"""
import hashlib
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contracts" / "bounty_court.py"


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n")
    # 'genlayer code' prints a leading blank line and a 'Result:' banner.
    text = re.sub(r"^\n?Result:\n", "", text)
    return text.rstrip() + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[4].strip())
        return 2
    address = sys.argv[1]
    out = subprocess.run(
        ["genlayer", "code", address],
        capture_output=True,
        text=True,
        check=True,
        # On Windows 'genlayer' is a .cmd shim, which CreateProcess cannot launch.
        shell=(os.name == "nt"),
    )
    local = normalise(CONTRACT.read_text(encoding="utf-8"))
    chain = normalise(out.stdout)
    print("local  ", digest(local), len(local.encode("utf-8")), "B")
    print("chain  ", digest(chain), len(chain.encode("utf-8")), "B")
    if local == chain:
        print("MATCH")
        return 0
    print("MISMATCH")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
