"""Offline check for the pinned Retraction Watch CSV. The server never runs this.

Usage: uv run python scripts/freeze_retraction_watch.py /path/to/retraction_watch.csv
"""

import gzip
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retraction_agent.config import ROOT

EXPECTED_SHA = "e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea"
EXPECTED_BYTES = 67868852


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("pass the path to retraction_watch.csv from commit fb5f174f")
    raw = Path(sys.argv[1]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA or len(raw) != EXPECTED_BYTES:
        raise SystemExit(f"refusing to write: sha {digest} bytes {len(raw)}")
    target = ROOT / "data" / "retraction_watch.csv.gz"
    target.write_bytes(gzip.compress(raw, compresslevel=9))
    print(target, hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
