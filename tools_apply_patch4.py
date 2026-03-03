from __future__ import annotations
from pathlib import Path

FILE = Path("trade_live.py")

MARK_START = "# --- PATCH4: HEARTBEAT (AUTO) START ---"
MARK_END   = "# --- PATCH4: HEARTBEAT (AUTO) END ---"

BLOCK = f"""{MARK_START}
import json
from pathlib import Path

_RUNTIME_DIR = Path(os.environ.get("BOT_RUNTIME_DIR", ".runtime"))
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
_HEARTBEAT_PATH = _RUNTIME_DIR / "heartbeat.json"

def _write_heartbeat(symbol: str | None = None, note: str | None = None) -> None:
    try:
        _HEARTBEAT_PATH.write_text(
            json.dumps({{"ts": time.time(), "symbol": symbol, "note": note}}),
            encoding="utf-8",
        )
    except Exception:
        pass
{MARK_END}
"""

def die(msg: str) -> None:
    raise SystemExit(msg)

src = FILE.read_text(encoding="utf-8")

if MARK_START not in src:
    src = BLOCK + "\n" + src

needle_while = "    while True:\n"
if needle_while not in src:
    die("Cannot find 'while True:' in trade_live.py")

if "note='loop_start'" not in src:
    src = src.replace(needle_while, needle_while + "        _write_heartbeat(symbol=None, note='loop_start')\n", 1)

needle_before_order = "                res = place_market_order_with_tp_sl(\n"
if needle_before_order in src and "note='before_order'" not in src:
    src = src.replace(needle_before_order, "                _write_heartbeat(symbol=symbol, note='before_order')\n" + needle_before_order, 1)

FILE.write_text(src, encoding="utf-8")
print("OK: Patch4 heartbeat injected into trade_live.py")
