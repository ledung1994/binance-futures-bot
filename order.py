#!/usr/bin/env python3
"""
Order helpers:
- place_market_order_with_tp_sl(): đặt MARKET và tự đặt TP/SL theo ATR
"""
import logging
from market import (
    place_market_order,
    place_stop_loss_order,
    place_take_profit_order,
    calc_take_profit_levels,
)

log = logging.getLogger("order")


def place_market_order_with_tp_sl(symbol, side, quantity, atr, tp_mult=2.0, sl_mult=1.5, min_notional_usdt=20.0):
    """
    Returns dict:
      {
        "order": <market_order_resp>,
        "entry_price": float,
        "qty": float,
        "tp_order": <tp_resp or None>,
        "sl_order": <sl_resp or None>,
        "tp_price": float,
        "sl_price": float,
      }
    """
    mkt = place_market_order(symbol, side, quantity, min_notional_usdt=min_notional_usdt)
    if not mkt:
        return None

    entry_price = float(mkt.get("_entry_price") or 0.0)
    qty = float(mkt.get("_qty") or quantity)
    atr = float(atr or 0.0)

    if entry_price <= 0 or atr <= 0:
        log.warning("Skip TP/SL: entry_price=%.8f atr=%.8f", entry_price, atr)
        return {
            "order": mkt,
            "entry_price": entry_price,
            "qty": qty,
            "tp_order": None,
            "sl_order": None,
            "tp_price": 0.0,
            "sl_price": 0.0,
        }

    tp_price, sl_price = calc_take_profit_levels(entry_price, atr, side=side, tp_mult=tp_mult, sl_mult=sl_mult)

    tp_order = place_take_profit_order(symbol, side, qty, tp_price)
    sl_order = place_stop_loss_order(symbol, side, qty, sl_price)

    log.info(
        "TP/SL placed: %s side=%s entry=%.8f atr=%.8f TP=%.8f SL=%.8f tpOrderId=%s slOrderId=%s",
        symbol, side, entry_price, atr, tp_price, sl_price,
        (tp_order or {}).get("orderId"), (sl_order or {}).get("orderId")
    )

    return {
        "order": mkt,
        "entry_price": entry_price,
        "qty": qty,
        "tp_order": tp_order,
        "sl_order": sl_order,
        "tp_price": tp_price,
        "sl_price": sl_price,
    }
