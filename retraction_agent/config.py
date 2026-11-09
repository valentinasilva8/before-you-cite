"""Load the committed config. The only runtime environment variable is PORT, and uvicorn reads it."""

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_config() -> dict:
    path = ROOT / "config" / "config.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def limits() -> dict:
    return load_config()["limits"]
