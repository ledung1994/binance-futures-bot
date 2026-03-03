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

def calc_take_profit_levels(entry_price, atr, tp_mult=2.0, sl_mult=1.5):
tp_price = entry_price + atr * tp_mult
sl_price = entry_price - atr * sl_mult
return tp_price, sl_price

def get_symbol_info(client, symbol):
data = {"step_size": 0.001, "min_qty": 0.001, "max_qty": 1e18,
"quantityPrecision": 3, "pricePrecision": 2, "tick_size": 0.01}
return data

def place_market_order(symbol, side, quantity, min_notional_usdt=20.0):
client = get_client()
info = get_symbol_info(client, symbol)

step = float(info.get("step_size", 0.001))
min_qty = float(info.get("min_qty", 0.001))
max_qty = float(info.get("max_qty", 1e18))
qty = float(quantity)
qty = math.floor(qty / step) * step
prec = int(info.get("quantityPrecision", 3))
qty = float(f"{qty:.{prec}f}")

if qty <= 0:
    log.warning("Calculated qty too small for %s (min_qty=%s). Skip.", symbol, min_qty)
    return None

price = get_mark_price(client, symbol)
notional = qty * price
if price <= 0:
    log.warning("Mark price unavailable for %s. Skip.", symbol)
    return None
if notional < float(min_notional_usdt):
    log.warning("Notional too small for %s: %.4f < %.2f. Skip.", symbol, notional, min_notional_usdt)
    return None

try:
    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=str(qty),
        newOrderRespType="RESULT",
    )
    avg_price = float(order.get("avgPrice") or 0.0)
    if avg_price <= 0:
        cum_quote = float(order.get("cumQuote") or 0.0)
        exec_qty = float(order.get("executedQty") or 0.0)
        if exec_qty > 0 and cum_quote > 0:
            avg_price = cum_quote / exec_qty
    if avg_price <= 0:
        fills = order.get("fills") or []
        if fills:
            total_qty = sum(float(f.get("qty")) for f in fills)
            total_cost = sum(float(f.get("qty")) * float(f.get("price")) for f in fills)
            if total_qty > 0:
                avg_price = total_cost / total_qty
    if avg_price <= 0:
        avg_price = price
        log.warning("avgPrice=0 from API for %s, using mark price %.8f as fallback", symbol, price)

    log.info("MARKET ORDER placed: %s %s qty=%s avgPrice=%.8f cumQuote=%s execQty=%s status=%s orderId=%s",
             side, symbol, qty, avg_price, order.get("cumQuote"), order.get("executedQty"), order.get("status"), order.get("orderId"))
    trade_data = {
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "entry_price": avg_price,
        "status": order.get("status"),
        "orderId": order.get("orderId"),
    }
    try:
        log_trade(trade_data)
    except Exception:
        log.exception("log_trade failed (non-fatal)")
    order["_entry_price"] = avg_price
    order["_qty"] = qty
    return order
except Exception as e:
    log.exception("Failed to place market order %s %s qty=%s: %s", side, symbol, qty, e)
    return None
def place_stop_loss_order(symbol, side, quantity, stop_price):
try:
sl_side = "SELL" if side == "BUY" else "BUY"
client = get_client()
return client.futures_create_order(symbol=symbol, side=sl_side, type="STOP_MARKET",
stopPrice=str(stop_price), quantity=str(quantity),
closePosition="true", newOrderRespType="RESULT")
except Exception as e:
log.exception("Failed SL for %s: %s", symbol, e)
return None

def place_take_profit_order(symbol, side, quantity, tp_price):
try:
tp_side = "SELL" if side == "BUY" else "BUY"
client = get_client()
return client.futures_create_order(symbol=symbol, side=tp_side, type="TAKE_PROFIT_MARKET",
stopPrice=str(tp_price), quantity=str(quantity),
closePosition="true", newOrderRespType="RESULT")
except Exception as e:
log.exception("Failed TP for %s: %s", symbol, e)
return None
