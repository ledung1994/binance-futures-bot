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
    return float(mp.get("markPrice", 0.0))


def calc_take_profit_levels(entry_price, atr, side=None, tp_mult=2.0, sl_mult=1.5):
    """
    Backward-compatible:
      - Old signature: (entry_price, atr, tp_mult, sl_mult) for LONG
      - New: provide side='BUY' (long) or 'SELL' (short)
    Returns (tp_price, sl_price)
    """
    entry_price = float(entry_price)
    atr = float(atr)

    if not side or str(side).upper() == "BUY":
        tp_price = entry_price + atr * float(tp_mult)
        sl_price = entry_price - atr * float(sl_mult)
    else:
        tp_price = entry_price - atr * float(tp_mult)
        sl_price = entry_price + atr * float(sl_mult)

    return tp_price, sl_price


def get_symbol_info(client, symbol):
    # Minimal fallback (bạn có thể thay bằng exchangeInfo cho chuẩn tick/step)
    return {
        "step_size": 0.001,
        "min_qty": 0.001,
        "max_qty": 1e18,
        "quantityPrecision": 3,
        "pricePrecision": 2,
        "tick_size": 0.01,
    }


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


def cancel_all_open_orders(symbol, client=None):
    """
    Huỷ toàn bộ open orders của symbol để tránh chồng SL/TP cũ.
    """
    c = client or get_client()
    try:
        c.futures_cancel_all_open_orders(symbol=symbol)
        log.info("Canceled all open orders for %s", symbol)
        return True
    except Exception as e:
        log.warning("Could not cancel open orders for %s: %s", symbol, e)
        return False

def place_market_order(symbol, side, quantity, min_notional_usdt=20.0, client=None):
    """
    Place MARKET Futures order.
    - Tự round qty theo step
    - Check min notional
    - Lấy entry_price từ response (avgPrice/cumQuote/executedQty/fills), fallback mark price
    - Trả về dict order có thêm: _entry_price, _qty
    """
    c = client or get_client()

    side = str(side).upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"Invalid side: {side}")

    info = get_symbol_info(c, symbol)
    step = info.get("step_size", 0.001)
    qty_prec = info.get("quantityPrecision", 3)

    qty = _round_to_step(float(quantity), step, qty_prec)
    if qty <= 0:
        log.warning("place_market_order: qty<=0 after rounding for %s (raw=%s)", symbol, quantity)
        return None

    # Fallback price dùng mark price để check notional + fallback entry
    try:
        mark = get_mark_price(c, symbol)
    except Exception:
        mark = 0.0

    min_notional = float(min_notional_usdt or 0.0)
    if min_notional > 0 and mark > 0 and (qty * mark) < min_notional:
        log.warning(
            "Notional too small for %s: qty=%.8f mark=%.8f notional=%.4f < min=%.4f",
            symbol, qty, mark, qty * mark, min_notional
        )
        return None

    try:
        order = c.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=str(qty),
            newOrderRespType="RESULT",
        )
    except Exception as e:
        log.exception("Failed MARKET order %s %s qty=%s: %s", side, symbol, qty, e)
        return None

    entry_price = _extract_entry_price(order or {}, mark)

    # attach helper fields for main.py
    if isinstance(order, dict):
        order["_entry_price"] = float(entry_price or 0.0)
        order["_qty"] = float(qty)
    return order

def place_stop_loss_order(symbol, side, quantity, stop_price, client=None, position_side=None, **kwargs):
    """
    Stop loss reduceOnly theo quantity.
    workingType=MARK_PRICE giúp ổn định hơn.
    """
    c = client or get_client()
    try:
        sl_side = "SELL" if str(side).upper() == "BUY" else "BUY"
        info = get_symbol_info(c, symbol)

        qty = _round_to_step(float(quantity), info.get("step_size", 0.001), info.get("quantityPrecision", 3))
        sp = _round_to_tick(float(stop_price), info.get("tick_size", 0.01), info.get("pricePrecision", 2))

        return c.futures_create_order(
            symbol=symbol,
            side=sl_side,
            type="STOP_MARKET",
            stopPrice=str(sp),
            quantity=str(qty),
            reduceOnly="true",
            workingType="MARK_PRICE",
            newOrderRespType="RESULT",
        )
    except Exception as e:
        log.exception("Failed SL for %s: %s", symbol, e)
        return None


def place_take_profit_order(symbol, side, quantity, tp_price, client=None, position_side=None, **kwargs):
    """
    Take profit reduceOnly theo quantity.
    """
    c = client or get_client()
    try:
        tp_side = "SELL" if str(side).upper() == "BUY" else "BUY"
        info = get_symbol_info(c, symbol)

        qty = _round_to_step(float(quantity), info.get("step_size", 0.001), info.get("quantityPrecision", 3))
        tp = _round_to_tick(float(tp_price), info.get("tick_size", 0.01), info.get("pricePrecision", 2))

        return c.futures_create_order(
            symbol=symbol,
            side=tp_side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=str(tp),
            quantity=str(qty),
            reduceOnly="true",
            workingType="MARK_PRICE",
            newOrderRespType="RESULT",
        )
    except Exception as e:
        log.exception("Failed TP for %s: %s", symbol, e)
        return None

def has_protection_orders(symbol, client=None, position_side=None):
    """
    Trả True nếu có đủ SL + TP (các lệnh reduceOnly/closePosition) đang OPEN.
    position_side: None (không lọc), hoặc 'LONG'/'SHORT'/'BOTH'
    """
    c = client or get_client()
    orders = c.futures_get_open_orders(symbol=symbol)

    sl_types = {"STOP_MARKET", "STOP", "STOP_LOSS", "STOP_LOSS_LIMIT"}
    tp_types = {"TAKE_PROFIT_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"}

    has_sl = False
    has_tp = False

    for o in orders:
        t = str(o.get("type") or "").upper()

        # Lọc positionSide nếu bạn chạy hedge mode
        if position_side:
            ps = str(o.get("positionSide") or "").upper()
            if ps and ps != position_side.upper():
                continue

        # Chỉ coi là protection nếu là lệnh đóng vị thế
        # (reduceOnly hoặc closePosition)
        reduce_only = bool(o.get("reduceOnly"))
        close_pos = bool(o.get("closePosition"))
        if not (reduce_only or close_pos):
            continue

        if t in sl_types:
            has_sl = True
        elif t in tp_types:
            has_tp = True

    return has_sl and has_tp

def place_tp_sl(symbol, side, quantity, sl_price, tp_price, client=None, cancel_existing=True, position_side=None):
    """
    Đặt TP + SL cho vị thế đang mở.
    side = side của ENTRY (BUY/SELL).
    cancel_existing=True thì huỷ toàn bộ open orders (cẩn thận nếu hedge nhiều lệnh).
    position_side: 'BOTH' (one-way) hoặc 'LONG'/'SHORT' (hedge). Nếu None thì không set.
    """
    c = client or get_client()

    if cancel_existing:
        cancel_all_open_orders(symbol, client=c)

    # Đặt SL/TP bằng các hàm bạn đang có.
    # Quan trọng: nên truyền client=c (để không bị dùng client khác / config khác)
    sl_order = place_stop_loss_order(symbol, side, quantity, sl_price, client=c, position_side=position_side)
    tp_order = place_take_profit_order(symbol, side, quantity, tp_price, client=c, position_side=position_side)

    ok_sl = bool(sl_order and sl_order.get("orderId"))
    ok_tp = bool(tp_order and tp_order.get("orderId"))

    log.info(
        "Placed protection for %s: SL=%s (id=%s) | TP=%s (id=%s)",
        symbol,
        sl_price, (sl_order or {}).get("orderId"),
        tp_price, (tp_order or {}).get("orderId"),
    )

    return {"sl": sl_order, "tp": tp_order, "ok_sl": ok_sl, "ok_tp": ok_tp}

def get_open_position(symbol, client=None):
    c = client or get_client()
    poss = c.futures_position_information(symbol=symbol)
    for p in poss:
        if p.get("symbol") == symbol:
            amt = float(p.get("positionAmt") or 0.0)
            if amt != 0.0:
                entry = float(p.get("entryPrice") or 0.0)
                return {"amt": amt, "entryPrice": entry, "raw": p}
    return None

def has_protection_orders(symbol, client=None):
    c = client or get_client()
    orders = c.futures_get_open_orders(symbol=symbol)

    sl_types = {"STOP_MARKET", "STOP", "STOP_LOSS", "STOP_LOSS_LIMIT"}
    tp_types = {"TAKE_PROFIT_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"}

    has_sl = False
    has_tp = False

    for o in orders:
        t = str(o.get("type") or "").upper()

        # Chỉ tính là protection nếu là lệnh đóng vị thế (reduceOnly/closePosition)
        reduce_only = bool(o.get("reduceOnly"))
        close_pos = bool(o.get("closePosition"))
        if not (reduce_only or close_pos):
            continue

        if t in sl_types:
            has_sl = True
        elif t in tp_types:
            has_tp = True

    return has_sl and has_tp
