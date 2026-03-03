#!/usr/bin/env python3
"""Order Manager — Places REAL orders on Binance Futures USDT-M."""
import os
import logging
import numpy as np
from binance.client import Client

log = logging.getLogger("order")
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("BINANCE_API_KEY", "")
        api_secret = os.environ.get("BINANCE_API_SECRET", "")
        use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"
        if not api_key or not api_secret:
            raise ValueError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
        _client = Client(api_key, api_secret, testnet=use_testnet)
        log.info("Binance client initialized. Testnet=%s", use_testnet)
    return _client

def get_symbol_info(client, symbol):
    info = client.futures_exchange_info()
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            qty_precision = s.get("quantityPrecision", 3)
            price_precision = s.get("pricePrecision", 2)
            step_size = 0.001
            min_qty = 0.001
            max_qty = float("inf")
            for f in s.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f.get("stepSize", step_size))
                    min_qty = float(f.get("minQty", min_qty))
                    max_qty = float(f.get("maxQty", max_qty))
            return {"qty_precision": qty_precision, "price_precision": price_precision, "step_size": step_size, "min_qty": min_qty, "max_qty": max_qty}
    return {"qty_precision": 3, "price_precision": 2, "step_size": 0.001, "min_qty": 0.001, "max_qty": float("inf")}

def format_quantity(quantity, symbol_info):
    step_size = float(symbol_info.get("step_size", 0.001))
    prec = int(abs(np.log10(step_size))) if step_size < 1 else 0
    q = float(f"{quantity:.{prec}f}")
    return q

def place_market_order(symbol, side, quantity):
    client = get_client()
    si = get_symbol_info(client, symbol)
    qty = format_quantity(quantity, si)
    if qty < si["min_qty"] or qty > si["max_qty"]:
        log.warning("Invalid qty=%s for %s (min=%s max=%s)", qty, symbol, si["min_qty"], si["max_qty"])
        return None

    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=qty,
        newOrderRespType="FULL",
    )
    log.info("MARKET ORDER: %s %s %s | orderId=%s status=%s avgPrice=%s",
             side, qty, symbol, order.get("orderId"), order.get("status"), order.get("avgPrice"))
    return order
