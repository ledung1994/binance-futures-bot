from __future__ import annotations
from pathlib import Path

FILES = [Path("main.py"), Path("trade_live.py")]

MARK_START = "# --- PATCH3: LOG MASKING (AUTO) START ---"
MARK_END   = "# --- PATCH3: LOG MASKING (AUTO) END ---"

BLOCK = f"""{MARK_START}
# Mask secrets in logs (BINANCE_API_KEY / BINANCE_API_SECRET)
try:
    from log_masking import install_log_masking
    install_log_masking()
except Exception:
    pass
{MARK_END}
"""

def inject(path: Path) -> None:
    if not path.exists():
        return
    s = path.read_text(encoding="utf-8")
    if MARK_START in s:
        return

    # Place right after PATCH2 dotenv block if present; else at top
    idx = s.find("# --- PATCH2: DOTENV (AUTO) END ---")
    if idx != -1:
        insert_at = idx + len("# --- PATCH2: DOTENV (AUTO) END ---")
        s2 = s[:insert_at] + "\n\n" + BLOCK + "\n" + s[insert_at:]
    else:
        s2 = BLOCK + "\n" + s

    path.write_text(s2, encoding="utf-8")
    print(f"Injected log masking into {path}")

for f in FILES:
    inject(f)
