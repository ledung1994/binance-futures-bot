import json
import os
import sys
import time
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("BOT_RUNTIME_DIR", ".runtime"))
HEARTBEAT = RUNTIME_DIR / "heartbeat.json"
MAX_AGE_SEC = int(os.environ.get("BOT_HEALTH_MAX_AGE_SEC", "90"))

def main() -> int:
    if not HEARTBEAT.exists():
        print(f"UNHEALTHY: missing {HEARTBEAT}")
        return 2
    try:
        data = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        ts = float(data.get("ts", 0))
    except Exception as e:
        print(f"UNHEALTHY: bad heartbeat: {e}")
        return 3

    age = time.time() - ts
    if age > MAX_AGE_SEC:
        print(f"UNHEALTHY: heartbeat stale age={age:.1f}s > {MAX_AGE_SEC}s")
        return 4

    print(f"OK: age={age:.1f}s symbol={data.get('symbol')} note={data.get('note')}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
