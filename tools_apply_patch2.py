from __future__ import annotations
from pathlib import Path

FILES = [Path("main.py"), Path("trade_live.py")]

MARK_START = "# --- PATCH2: DOTENV (AUTO) START ---"
MARK_END   = "# --- PATCH2: DOTENV (AUTO) END ---"

BLOCK = f"""{MARK_START}
# Load .env automatically (do not commit .env)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
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

    # inject right after shebang if present, else at top
    if s.startswith("#!/"):
        lines = s.splitlines(True)
        # after first line
        s2 = lines[0] + "\n" + BLOCK + "\n" + "".join(lines[1:])
    else:
        s2 = BLOCK + "\n" + s

    path.write_text(s2, encoding="utf-8")
    print(f"Injected dotenv into {path}")

for f in FILES:
    inject(f)
