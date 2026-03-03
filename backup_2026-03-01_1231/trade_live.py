import os, time
from utils import log, load_config
from binance.client import Client

import market
import strategy
import order

def main():
    cfg = load_config()

    api_key = os.environ.get("BINANCE_API_KEY") or cfg.get("api_key")
    api_secret = os.environ.get("BINANCE_API_SECRET") or cfg.get("api_secret")
    use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"

    if not api_key or not api_secret:
        log.error("Missing Binance API credentials.")
        return

    client = Client(api_key, api_secret, testnet=use_testnet)
    log.info("TRADE LOOP STARTED. Testnet=%s", use_testnet)

    top_n = int(cfg.get("volume_count", 20))
    qty = float(cfg.get("order_qty", 0.001))
    loop_sleep = int(cfg.get("loop_sleep", 10))

    while True:
        try:
            symbols = market.get_top_volume_symbols(client, top_n=top_n)

            if not symbols:
                log.warning("No symbols returned; sleeping.")
                time.sleep(loop_sleep)
                continue

            # market.py thường trả list[str]; nếu trả list[dict] thì normalize
            if symbols and isinstance(symbols[0], dict) and "symbol" in symbols[0]:
                symbols = [x["symbol"] for x in symbols]

            log.info("Scanning %d symbols (first 10): %s", len(symbols), ",".join(symbols[:10]))

            for sym in symbols:
                sig = strategy.generate_signal(client, sym, cfg)
                if not sig:
                    continue

                side = sig["side"]  # BUY / SELL
                log.info("[ORDER] placing %s %s qty=%s", side, sym, qty)
                order.place_market_order(sym, side, qty)
                time.sleep(1)

            time.sleep(loop_sleep)

        except Exception as e:
            log.exception("Trade loop error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
