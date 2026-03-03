from __future__ import annotations
from pathlib import Path

FILE = Path("trade_live.py")

PATCH_TOP_START = "# --- PATCH1: GUARDRAILS (AUTO) START ---"
PATCH_TOP_END   = "# --- PATCH1: GUARDRAILS (AUTO) END ---"

PATCH_LOOP_START = "        # --- PATCH1: GUARDRAILS CHECK (AUTO) START ---"
PATCH_LOOP_END   = "        # --- PATCH1: GUARDRAILS CHECK (AUTO) END ---"

PATCH_POS_START  = "                # --- PATCH1: POSITION GUARDRAIL (AUTO) START ---"
PATCH_POS_END    = "                # --- PATCH1: POSITION GUARDRAIL (AUTO) END ---"

def die(msg: str) -> None:
    raise SystemExit(msg)

src = FILE.read_text(encoding="utf-8")

# 1) Insert guardrails helpers at top (after imports is hard; so we prepend but keep idempotent markers)
top_block = f"""{PATCH_TOP_START}
import os
import logging

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)

def _futures_equity_usdt(client):
    \"\"\"Return (equity, wallet, unrealized) in USDT. Uses python-binance futures_account() if available.\"\"\"
    try:
        acc = client.futures_account()
        wallet = _safe_float(acc.get("totalWalletBalance", 0.0))
        upnl = _safe_float(acc.get("totalUnrealizedProfit", 0.0))
        equity = wallet + upnl
        return equity, wallet, upnl
    except Exception:
        # fallback: wallet only
        try:
            bal = client.futures_account_balance()
            wallet = 0.0
            for it in bal:
                if str(it.get("asset", "")).upper() in ("USDT", "BUSD"):
                    wallet = _safe_float(it.get("balance", 0.0))
                    break
            return wallet, wallet, 0.0
        except Exception:
            return 0.0, 0.0, 0.0

def _position_notional_usdt(client, symbol: str) -> float:
    \"\"\"Estimate position notional = abs(positionAmt) * markPrice.\"\"\"
    try:
        info = client.futures_position_information(symbol=symbol)
        if isinstance(info, list) and info:
            info = info[0]
        amt = _safe_float(info.get("positionAmt", 0.0))
        mark = _safe_float(info.get("markPrice", 0.0))
        return abs(amt) * mark
    except Exception:
        return 0.0
{PATCH_TOP_END}
"""

if PATCH_TOP_START not in src:
    src = top_block + "\n" + src

# 2) Insert guardrails state init before `while True:`
needle_init = "    while True:\n"
if needle_init not in src:
    die("Không tìm thấy 'while True:' trong trade_live.py (đúng snippet bạn gửi phải có).")

# Put state init immediately before while True
init_block = (
    "    # --- PATCH1: GUARDRAILS STATE (AUTO) ---\n"
    "    max_drawdown_pct = _safe_float(cfg.get('MAX_DRAWDOWN_PCT', cfg.get('max_drawdown_pct', 2.0)), 2.0)\n"
    "    max_position_pct = _safe_float(cfg.get('MAX_POSITION_PCT', cfg.get('max_position_pct', 1.0)), 1.0)\n"
    "    equity_peak = None\n"
    "    circuit_breaker_active = False\n\n"
)
if init_block not in src:
    src = src.replace(needle_init, init_block + needle_init, 1)

# 3) Insert per-outer-loop guardrails check at top of while True loop
# We insert right after `while True:` line (one indentation level inside)
loop_insert_point = "    while True:\n"
loop_block = (
    f"{PATCH_LOOP_START}\n"
    "        # Hard kill-switch via env\n"
    "        if str(os.environ.get('BINANCE_KILL_SWITCH', 'false')).lower() == 'true':\n"
    "            logging.getLogger('bot.trade_live').warning('BINANCE_KILL_SWITCH=true -> stopping trading loop iteration')\n"
    "            time.sleep(max(5.0, loop_sleep))\n"
    "            continue\n\n"
    "        # Update equity peak + drawdown\n"
    "        try:\n"
    "            equity, wallet, upnl = _futures_equity_usdt(client)\n"
    "            if equity_peak is None:\n"
    "                equity_peak = equity\n"
    "            equity_peak = max(equity_peak, equity)\n"
    "            drawdown_pct = 0.0\n"
    "            if equity_peak and equity_peak > 0:\n"
    "                drawdown_pct = max(0.0, (equity_peak - equity) / equity_peak * 100.0)\n"
    "            if drawdown_pct >= max_drawdown_pct:\n"
    "                circuit_breaker_active = True\n"
    "                logging.getLogger('bot.trade_live').warning(\n"
    "                    'CIRCUIT BREAKER: drawdown %.4f%% >= %.4f%% (equity=%.4f wallet=%.4f upnl=%.4f peak=%.4f)',\n"
    "                    drawdown_pct, max_drawdown_pct, equity, wallet, upnl, equity_peak\n"
    "                )\n"
    "        except Exception as e:\n"
    "            logging.getLogger('bot.trade_live').exception('Guardrails equity/drawdown error: %s', e)\n"
    "            wallet = None\n\n"
    "        if circuit_breaker_active:\n"
    "            logging.getLogger('bot.trade_live').warning('Circuit-breaker ACTIVE -> skip all trades this cycle')\n"
    "            time.sleep(max(5.0, loop_sleep))\n"
    "            continue\n"
    f"{PATCH_LOOP_END}\n"
)

if PATCH_LOOP_START not in src:
    src = src.replace(loop_insert_point, loop_insert_point + loop_block, 1)

# 4) Insert per-symbol position guardrail right before place_market_order_with_tp_sl call
call_needle = "                res = place_market_order_with_tp_sl(\n"
if call_needle not in src:
    die("Không tìm thấy chỗ gọi place_market_order_with_tp_sl(...) trong trade_live.py.")

pos_block = (
    f"{PATCH_POS_START}\n"
    "                try:\n"
    "                    if wallet is not None:\n"
    "                        pos_notional = _position_notional_usdt(client, symbol)\n"
    "                        pos_pct = (pos_notional / max(1e-6, float(wallet))) * 100.0\n"
    "                        if pos_pct > max_position_pct:\n"
    "                            circuit_breaker_active = True\n"
    "                            logging.getLogger('bot.trade_live').warning(\n"
    "                                'CIRCUIT BREAKER: position %.4f%% > %.4f%% (symbol=%s notional=%.4f wallet=%.4f)',\n"
    "                                pos_pct, max_position_pct, symbol, pos_notional, float(wallet)\n"
    "                            )\n"
    "                            break\n"
    "                except Exception as e:\n"
    "                    logging.getLogger('bot.trade_live').exception('Guardrails position error: %s', e)\n"
    f"{PATCH_POS_END}\n"
)

if PATCH_POS_START not in src:
    src = src.replace(call_needle, pos_block + call_needle, 1)

FILE.write_text(src, encoding="utf-8")
print("OK: Patch1 guardrails injected into trade_live.py")
