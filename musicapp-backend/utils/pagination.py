import json
import urllib.parse
from typing import Optional, Dict


def encode_last_key(last_key: Optional[Dict]) -> Optional[str]:
    if not last_key:
        return None
    return urllib.parse.quote(json.dumps(last_key))


def decode_last_key(s: Optional[str]) -> Optional[Dict]:
    if not s:
        return None
    try:
        return json.loads(urllib.parse.unquote(s))
    except Exception:
        return None
