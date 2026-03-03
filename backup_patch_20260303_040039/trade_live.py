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

    while True:
        now = datetime.now(timezone.utc).isoformat()
        for symbol in symbols:
            try:
                last = generate_signal(client, symbol, cfg)
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
