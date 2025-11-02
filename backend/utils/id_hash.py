import json
import hashlib
from typing import Any


def content_hash(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()



