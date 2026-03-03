import csv
import os
import time
from pathlib import Path

def _runtime_dir() -> Path:
    d = Path(os.environ.get("BOT_RUNTIME_DIR", ".runtime"))
    d.mkdir(parents=True, exist_ok=True)
    return d

def paper_record_trade(row: dict) -> None:
    path = _runtime_dir() / "paper_trades.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if is_new:
            w.writeheader()
        w.writerow(row)

def paper_place_market_order_with_tp_sl(
    symbol: str,
    side: str,
    quantity: float,
    atr: float,
    tp_mult: float,
    sl_mult: float,
    min_notional_usdt: float = 0.0,
) -> dict:
    # NOTE: This does NOT place a real order.
    # It records an intent with computed TP/SL distances from ATR.
    now = time.time()
    row = {
        "ts": now,
        "symbol": symbol,
        "side": side,
        "qty": quantity,
        "atr": atr,
        "tp_mult": tp_mult,
        "sl_mult": sl_mult,
        "min_notional_usdt": min_notional_usdt,
        "mode": "PAPER",
    }
    paper_record_trade(row)
    return {"ok": True, "mode": "PAPER", "recorded": row}
