#!/usr/bin/env python3
import os
import time
import logging
from datetime import datetime, timezone
from binance.client import Client
from utils import log, load_config
import market
import strategy
import order

log = logging.getLogger("bot.trade")

def main():
cfg = load_config()
api_key = os.environ.get("BINANCE_API_KEY") or cfg.get("api_key")
api_secret = os.environ.get("BINANCE_API_SECRET") or cfg.get("api_secret")
use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"

client = Client(api_key, api_secret, testnet=use_testnet)
log.info("TRADE LOOP STARTED. Testnet=%s", use_testnet)

top_n = int(cfg.get("top_volume_count", 20))
loop_sleep = int(cfg.get("scan_interval_seconds", 20))
order_usd = float(cfg.get("order_usd", 25.0))
cooldown_sec = int(cfg.get("cooldown_seconds", 90))
max_trades = int(cfg.get("max_trades_per_day", 6))

cooldown = {}

while True:
    time.sleep(loop_sleep)
    try:
        client_symbols = market.get_top_volume_symbols(client, top_n=top_n)
        if not client_symbols:
            continue
        for sym in client_symbols:
            sig = strategy.generate_signal(client, sym, cfg)
            if not sig:
                continue
            if time.time() - cooldown.get(sym, 0) < cooldown_sec:
                continue
            side = sig["side"]
            price = float(sig.get("price") or 0.0)
            if price <= 0:
                continue
            qty = order_usd / price
            res = order.place_market_order(sym, side, qty)
            if res:
                cooldown[sym] = time.time()
                log.info("Trade occurred: %s %s %s", sym, side, qty)
    except Exception as e:
        log.exception("Test loop error: %s", e)
if name == "main":
main()
"""
