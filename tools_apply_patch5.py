from __future__ import annotations
from pathlib import Path

p = Path("trade_live.py")
s = p.read_text(encoding="utf-8").splitlines(True)

MARK_START = "# --- PATCH5: PAPER MODE (AUTO) START ---"
MARK_END   = "# --- PATCH5: PAPER MODE (AUTO) END ---"

# 1) Ensure import exists (near top after existing imports)
if not any("from paper import paper_place_market_order_with_tp_sl" in line for line in s):
    # insert after first blank line following shebang or after initial patch blocks
    insert_at = 0
    for i, line in enumerate(s):
        if line.strip() == "" and i > 0:
            insert_at = i + 1
            break
    s.insert(insert_at, f"{MARK_START}\nfrom paper import paper_place_market_order_with_tp_sl\n{MARK_END}\n\n")

# 2) Replace call site: res = place_market_order_with_tp_sl(...)
joined = "".join(s)
needle = "res = place_market_order_with_tp_sl("
if needle not in joined:
    raise SystemExit("Cannot find place_market_order_with_tp_sl call in trade_live.py")

# Insert conditional only once
if "paper_place_market_order_with_tp_sl(" not in joined:
    joined = joined.replace(
        "                res = place_market_order_with_tp_sl(",
        "                if _env_bool('PAPER_MODE', 'false'):\n"
        "                    logger.info('PAPER_MODE=true -> recording paper order %s %s qty=%.8f', side, symbol, qty)\n"
        "                    res = paper_place_market_order_with_tp_sl(\n"
        "                        symbol=symbol,\n"
        "                        side=side,\n"
        "                        quantity=qty,\n"
        "                        atr=atr,\n"
        "                        tp_mult=tp_mult,\n"
        "                        sl_mult=sl_mult,\n"
        "                        min_notional_usdt=min_notional,\n"
        "                    )\n"
        "                else:\n"
        "                    res = place_market_order_with_tp_sl(",
        1
    )

p.write_text(joined, encoding="utf-8")
print("OK: Patch5 injected into trade_live.py")
