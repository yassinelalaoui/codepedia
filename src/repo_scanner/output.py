from __future__ import annotations

import json
from .models import ScanResult


def serialize_scan_result(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

