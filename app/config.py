import os
from typing import Set


def load_api_keys() -> Set[str]:
    """Read allowed keys from GATEWAY_API_KEYS, e.g. 'key1,key2'."""
    raw = os.getenv("GATEWAY_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}