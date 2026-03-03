# --- PATCH4: HEARTBEAT (AUTO) START ---
import os
import json
from pathlib import Path

# --- PATCH5: PAPER MODE (AUTO) START ---
from paper import paper_place_market_order_with_tp_sl
# --- PATCH5: PAPER MODE (AUTO) END ---

_RUNTIME_DIR = Path(os.environ.get("BOT_RUNTIME_DIR", ".runtime"))
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
_HEARTBEAT_PATH = _RUNTIME_DIR / "heartbeat.json"

def _write_heartbeat(symbol: str | None = None, note: str | None = None) -> None:
    try:
        _HEARTBEAT_PATH.write_text(
            json.dumps({"ts": time.time(), "symbol": symbol, "note": note}),
            encoding="utf-8",
        )
    except Exception:
        pass
# --- PATCH4: HEARTBEAT (AUTO) END ---

# --- PATCH2: DOTENV (AUTO) START ---
# Load .env automatically (do not commit .env)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass
# --- PATCH2: DOTENV (AUTO) END ---

# --- PATCH3: LOG MASKING (AUTO) START ---
# Mask secrets in logs (BINANCE_API_KEY / BINANCE_API_SECRET)
try:
    from log_masking import install_log_masking
    install_log_masking()
except Exception:
    pass
# --- PATCH3: LOG MASKING (AUTO) END ---



# --- PATCH1: GUARDRAILS (AUTO) START ---
import os
import logging

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)

def _futures_equity_usdt(client):
    """Return (equity, wallet, unrealized) in USDT. Uses python-binance futures_account() if available."""
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
    """Estimate position notional = abs(positionAmt) * markPrice."""
    try:
        info = client.futures_position_information(symbol=symbol)
        if isinstance(info, list) and info:
            info = info[0]
        amt = _safe_float(info.get("positionAmt", 0.0))
        mark = _safe_float(info.get("markPrice", 0.0))
        return abs(amt) * mark
    except Exception:
        return 0.0
# --- PATCH1: GUARDRAILS (AUTO) END ---

#!/usr/bin/env python3
import os
import time
import logging
from datetime import datetime, timezone

from binance.client import Client
from utils import log, load_config
from strategy import generate_signal
from order import place_market_order_with_tp_sl

logger = logging.getLogger("bot.trade")


def _init_client():
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"
    c = Client(api_key, api_secret, testnet=use_testnet)
    logger.info("Binance client initialized. Testnet=%s", use_testnet)
    return c


def _decide_side(last, cfg):
    """
    Bạn thay logic này theo strategy hiện tại.
    Mặc định: EMA fast/slow + filter EMA200:
      - BUY nếu ema_fast > ema_slow và close > ema200
      - SELL nếu ema_fast < ema_slow và close < ema200
      - None nếu không rõ
    """
    close = float(last.get("close") or 0.0)
    ema_fast = float(last.get("ema_fast") or last.get("ema9") or 0.0)
    ema_slow = float(last.get("ema_slow") or last.get("ema21") or 0.0)
    ema200 = float(last.get("ema200") or 0.0)

    if close <= 0 or ema200 <= 0 or ema_fast <= 0 or ema_slow <= 0:
        return None

    if ema_fast > ema_slow and close > ema200:
        return "BUY"
    if ema_fast < ema_slow and close < ema200:
        return "SELL"
    return None


def main():
    cfg = load_config()
    client = _init_client()

    symbols = cfg.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [symbols]

    loop_sleep = float(cfg.get("loop_sleep", 10))
    min_notional = float(cfg.get("min_notional_usdt", 20.0))
    tp_mult = float(cfg.get("tp_mult", 2.0))
    sl_mult = float(cfg.get("sl_mult", 1.5))

    # qty config: có thể theo fixed_qty hoặc risk-based (tuỳ bot của bạn)
    fixed_qty = cfg.get("fixed_qty", None)

    logger.info("trade_live started. symbols=%s loop_sleep=%.1f", symbols, loop_sleep)

    # --- PATCH1: GUARDRAILS STATE (AUTO) ---
    max_drawdown_pct = _safe_float(cfg.get('MAX_DRAWDOWN_PCT', cfg.get('max_drawdown_pct', 2.0)), 2.0)
    max_position_pct = _safe_float(cfg.get('MAX_POSITION_PCT', cfg.get('max_position_pct', 1.0)), 1.0)
    equity_peak = None
    circuit_breaker_active = False

    while True:
        _write_heartbeat(symbol=None, note='loop_start')
        # --- PATCH1: GUARDRAILS CHECK (AUTO) START ---
        # Hard kill-switch via env
        if str(os.environ.get('BINANCE_KILL_SWITCH', 'false')).lower() == 'true':
            logging.getLogger('bot.trade_live').warning('BINANCE_KILL_SWITCH=true -> stopping trading loop iteration')
            time.sleep(max(5.0, loop_sleep))
            continue

        # Update equity peak + drawdown
        try:
            equity, wallet, upnl = _futures_equity_usdt(client)
            if equity_peak is None:
                equity_peak = equity
            equity_peak = max(equity_peak, equity)
            drawdown_pct = 0.0
            if equity_peak and equity_peak > 0:
                drawdown_pct = max(0.0, (equity_peak - equity) / equity_peak * 100.0)
            if drawdown_pct >= max_drawdown_pct:
                circuit_breaker_active = True
                logging.getLogger('bot.trade_live').warning(
                    'CIRCUIT BREAKER: drawdown %.4f%% >= %.4f%% (equity=%.4f wallet=%.4f upnl=%.4f peak=%.4f)',
                    drawdown_pct, max_drawdown_pct, equity, wallet, upnl, equity_peak
                )
        except Exception as e:
            logging.getLogger('bot.trade_live').exception('Guardrails equity/drawdown error: %s', e)
            wallet = None

        if circuit_breaker_active:
            logging.getLogger('bot.trade_live').warning('Circuit-breaker ACTIVE -> skip all trades this cycle')
            time.sleep(max(5.0, loop_sleep))
            continue
        # --- PATCH1: GUARDRAILS CHECK (AUTO) END ---
        now = datetime.now(timezone.utc).isoformat()
        for symbol in symbols:
            try:
                last = generate_signal(client, symbol, cfg)
                if last is None:
                    logger.warning('generate_signal returned None for %s; skipping', symbol)
                    continue
                side = _decide_side(last, cfg)
                if not side:
                    continue

                atr = float(last.get("atr") or 0.0)
                if atr <= 0:
                    continue

                qty = fixed_qty
                if qty is None:
                    # fallback đơn giản: cfg["qty"] hoặc 0.0
                    qty = float(cfg.get("qty", 0.0))
                qty = float(qty)

                if qty <= 0:
                    logger.warning("qty<=0 for %s. Set cfg.fixed_qty or cfg.qty", symbol)
                    continue

                logger.info("Signal %s %s atr=%.8f time=%s", side, symbol, atr, now)

                # --- PATCH1: POSITION GUARDRAIL (AUTO) START ---
                try:
                    if wallet is not None:
                        pos_notional = _position_notional_usdt(client, symbol)
                        pos_pct = (pos_notional / max(1e-6, float(wallet))) * 100.0
                        if pos_pct > max_position_pct:
                            circuit_breaker_active = True
                            logging.getLogger('bot.trade_live').warning(
                                'CIRCUIT BREAKER: position %.4f%% > %.4f%% (symbol=%s notional=%.4f wallet=%.4f)',
                                pos_pct, max_position_pct, symbol, pos_notional, float(wallet)
                            )
                            break
                except Exception as e:
                    logging.getLogger('bot.trade_live').exception('Guardrails position error: %s', e)
                # --- PATCH1: POSITION GUARDRAIL (AUTO) END ---
                _write_heartbeat(symbol=symbol, note='before_order')
                if _env_bool('PAPER_MODE', 'false'):
                    logger.info('PAPER_MODE=true -> recording paper order %s %s qty=%.8f', side, symbol, qty)
                    res = paper_place_market_order_with_tp_sl(
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        atr=atr,
                        tp_mult=tp_mult,
                        sl_mult=sl_mult,
                        min_notional_usdt=min_notional,
                    )
                else:
                    res = place_market_order_with_tp_sl(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    atr=atr,
                    tp_mult=tp_mult,
                    sl_mult=sl_mult,
                    min_notional_usdt=min_notional,
                )

                if not res:
                    continue

                # tránh spam liên tục nếu bạn chưa có quản lý vị thế; sleep thêm
                cool_down = float(cfg.get("cool_down_after_trade", 5))
                if cool_down > 0:
                    time.sleep(cool_down)

            except Exception as e:
                logger.exception("Loop error for %s: %s", symbol, e)

        time.sleep(loop_sleep)


if __name__ == "__main__":
    main()
