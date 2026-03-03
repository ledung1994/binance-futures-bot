#!/usr/bin/env python3
import os
import math
import logging
from binance.client import Client
from utils import log_trade

log = logging.getLogger("market")

_def_client = None


def get_client():
    global _def_client
    if _def_client is None:
        api_key = os.environ.get("BINANCE_API_KEY", "")
        api_secret = os.environ.get("BINANCE_API_SECRET", "")
        use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"
        _def_client = Client(api_key, api_secret, testnet=use_testnet)
        log.info("Binance client initialized. Testnet=%s", use_testnet)
    return _def_client


def get_mark_price(client, symbol):
    mp = client.futures_mark_price(symbol=symbol)
    price = float(mp.get("markPrice", 0.0))
    return price


def calc_take_profit_levels(entry_price, atr, side=None, tp_mult=2.0, sl_mult=1.5):
    """
    Backward-compatible:
      - Old signature: (entry_price, atr, tp_mult, sl_mult) for LONG
      - New: provide side='BUY' (long) or 'SELL' (short)
    Returns (tp_price, sl_price)
    """
    entry_price = float(entry_price)
    atr = float(atr)

    # If side is omitted, assume LONG like previous behavior
    if not side or str(side).upper() == "BUY":
        tp_price = entry_price + atr * float(tp_mult)
        sl_price = entry_price - atr * float(sl_mult)
    else:
        # Short: TP below, SL above
        tp_price = entry_price - atr * float(tp_mult)
        sl_price = entry_price + atr * float(sl_mult)

    return tp_price, sl_price


def get_symbol_info(client, symbol):
    # Minimal fallback (có thể thay bằng exchangeInfo nếu bạn muốn chuẩn hoá)
    data = {
        "step_size": 0.001,
        "min_qty": 0.001,
        "max_qty": 1e18,
        "quantityPrecision": 3,
        "pricePrecision": 2,
        "tick_size": 0.01,
    }
    return data


def _round_to_step(qty, step_size, quantity_precision):
    step = float(step_size or 0.001)
    q = float(qty)
    q = math.floor(q / step) * step
    prec = int(quantity_precision or 3)
    return float(f"{q:.{prec}f}")


def _round_to_tick(price, tick_size, price_precision=None):
    tick = float(tick_size or 0.01)
    p = float(price)
    p = math.floor(p / tick) * tick
    if price_precision is not None:
        prec = int(price_precision)
        p = float(f"{p:.{prec}f}")
    return p


def _extract_entry_price(order, fallback_price):
    """
    entry_price ưu tiên:
      1) avgPrice
      2) cumQuote / executedQty
      3) fills (nếu có)
      4) fallback_price (mark price)
    """
    avg_price = float(order.get("avgPrice") or 0.0)
    if avg_price > 0:
        return avg_price

    cum_quote = float(order.get("cumQuote") or 0.0)
    exec_qty = float(order.get("executedQty") or 0.0)
    if exec_qty > 0 and cum_quote > 0:
        return cum_quote / exec_qty

    fills = order.get("fills") or []
    if fills:
        total_qty = 0.0
        total_cost = 0.0
        for f in fills:
            fq = float(f.get("qty") or 0.0)
            fp = float(f.get("price") or 0.0)
            total_qty += fq
            total_cost += fq * fp
        if total_qty > 0:
            return total_cost / total_qty

    return float(fallback_price or 0.0)


def place_market_order(symbol, side, quantity, min_notional_usdt=20.0):
    client = get_client()
    info = get_symbol_info(client, symbol)

    step = float(info.get("step_size", 0.001))
    min_qty = float(info.get("min_qty", 0.001))
    max_qty = float(info.get("max_qty", 1e18))

    qty = float(quantity)
    qty = _round_to_step(qty, step, info.get("quantityPrecision", 3))

    if qty <= 0 or qty < min_qty:
        log.warning("Calculated qty too small for %s (min_qty=%s). Skip.", symbol, min_qty)
        return None
    if qty > max_qty:
        log.warning("Calculated qty too large for %s (max_qty=%s). Skip.", symbol, max_qty)
        return None

    price = get_mark_price(client, symbol)
    if price <= 0:
        log.warning("Mark price unavailable for %s. Skip.", symbol)
        return None

    notional = qty * price
    if notional < float(min_notional_usdt):
        log.warning(
            "Notional too small for %s: %.4f < %.2f. Skip.",
            symbol, notional, float(min_notional_usdt)
        )
        return None

    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=str(qty),
            newOrderRespType="RESULT",
        )

        entry_price = _extract_entry_price(order, price)
        if float(order.get("avgPrice") or 0.0) <= 0 and entry_price == price:
            log.warning("avgPrice=0 from API for %s, using mark price %.8f as fallback", symbol, price)

        log.info(
            "MARKET ORDER placed: %s %s qty=%s entry=%.8f cumQuote=%s execQty=%s status=%s orderId=%s",
            side, symbol, qty, entry_price, order.get("cumQuote"), order.get("executedQty"),
            order.get("status"), order.get("orderId")
        )

        trade_data = {
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "entry_price": entry_price,
            "status": order.get("status"),
            "orderId": order.get("orderId"),
        }

        try:
            log_trade(trade_data)
        except Exception:
            log.exception("log_trade failed (non-fatal)")

        # attach for convenience
        order["_entry_price"] = entry_price
        order["_qty"] = qty
        return order

    except Exception as e:
        log.exception("Failed to place market order %s %s qty=%s: %s", side, symbol, qty, e)
        return None


def place_stop_loss_order(symbol, side, quantity, stop_price):
    try:
        sl_side = "SELL" if side == "BUY" else "BUY"
        client = get_client()
        info = get_symbol_info(client, symbol)
        sp = _round_to_tick(stop_price, info.get("tick_size", 0.01), info.get("pricePrecision", 2))
        return client.futures_create_order(
            symbol=symbol,
            side=sl_side,
            type="STOP_MARKET",
            stopPrice=str(sp),
            quantity=str(quantity),
            closePosition="true",
            newOrderRespType="RESULT",
        )
    except Exception as e:
        log.exception("Failed SL for %s: %s", symbol, e)
        return None


def place_take_profit_order(symbol, side, quantity, tp_price):
    try:
        tp_side = "SELL" if side == "BUY" else "BUY"
        client = get_client()
        info = get_symbol_info(client, symbol)
        tp = _round_to_tick(tp_price, info.get("tick_size", 0.01), info.get("pricePrecision", 2))
        return client.futures_create_order(
            symbol=symbol,
            side=tp_side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=str(tp),
            quantity=str(quantity),
            closePosition="true",
            newOrderRespType="RESULT",
        )
    except Exception as e:
        log.exception("Failed TP for %s: %s", symbol, e)
        return None
