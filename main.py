#!/usr/bin/env python3

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



import os
import sys
import time

from utils import log, load_config, log_trade
from strategy import generate_signal
from risk import RiskManager
from market import get_symbol_info, place_market_order, place_tp_sl, get_open_position, has_protection_orders

def _env_bool(name: str, default: str = "false") -> bool:
    v = os.environ.get(name, default)
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _get_min_notional(cfg: dict) -> float:
    try:
        return float(cfg.get("min_notional_usdt", cfg.get("min_notional", 20.0)))
    except Exception:
        return 20.0


def _safe_place_market_order(place_fn, client, symbol, side, qty, min_notional):
    """
    Tương thích nhiều signature khác nhau của place_market_order.
    Ưu tiên gọi kiểu hiện tại: (symbol, side, qty, min_notional).
    """
    try:
        return place_fn(symbol, side, qty, min_notional)
    except TypeError:
        pass

    try:
        return place_fn(client, symbol, side, qty, min_notional)
    except TypeError:
        pass

    try:
        return place_fn(client, symbol, side, qty)
    except TypeError:
        pass

    return place_fn(symbol, side, qty)


def _get_available_balance(client) -> float:
    """Lấy availableBalance Futures để tránh lỗi -2019. Nếu API lỗi thì trả 0.0."""
    try:
        acc = client.futures_account()
        return float(acc.get("availableBalance") or 0.0)
    except Exception:
        return 0.0

def _get_position_amt(client, symbol: str) -> float:
    try:
        pos = client.futures_position_information(symbol=symbol)
        if not pos:
            return 0.0
        # futures_position_information trả list
        amt = float(pos[0].get("positionAmt") or 0.0)
        return amt
    except Exception:
        return 0.0


def _has_open_position(client, symbol: str) -> bool:
    return abs(_get_position_amt(client, symbol)) > 0.0

def main():
    cfg = load_config()

    paper = _env_bool("PAPER_MODE", "false")
    use_testnet = bool(cfg.get("use_testnet", False)) or _env_bool("BINANCE_USE_TESTNET", "false")
    leverage = int(os.environ.get("BINANCE_LEVERAGE", cfg.get("leverage", 5)))

    api_key = os.environ.get("BINANCE_API_KEY", cfg.get("api_key", ""))
    api_secret = os.environ.get("BINANCE_API_SECRET", cfg.get("api_secret", ""))

    mode = "TESTNET" if use_testnet else "LIVE"
    log.info("Binance Futures Bot (%s) starting. PAPER_MODE=%s.", mode, paper)

    if not api_key or not api_secret:
        log.error("Missing Binance API credentials. Set BINANCE_API_KEY and BINANCE_API_SECRET (systemd .env).")
        sys.exit(1)

    from binance.client import Client
    client = Client(api_key, api_secret, testnet=use_testnet)

    risk = RiskManager(cfg)
    risk.leverage = leverage
    risk.initial_balance = 0.0

    # Load initial balance (optional)
    try:
        acc = client.futures_account()
        bal = acc.get("availableBalance", acc.get("totalWalletBalance", 0.0))
        risk.initial_balance = float(bal or 0.0)
    except Exception as e:
        log.warning("Could not load initial balance: %s", e)

    symbols = cfg.get("symbols", ["BTCUSDT", "ETHUSDT"])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]

    scan_interval = int(cfg.get("scan_interval_seconds", 20))
    min_notional = _get_min_notional(cfg)
    max_margin_ratio = float(cfg.get("max_margin_ratio", 0.95))

    log.info("LIVE loop started. Scanning: %s", ", ".join(symbols))

    try:
        while True:
            if _env_bool("BINANCE_KILL_SWITCH", "false"):
                log.warning("BINANCE_KILL_SWITCH=true -> stopping bot.")
                break

            for symbol in symbols:
                try:
                    sig = generate_signal(client, symbol, cfg)

                    if sig is None:
                        continue

                    # Nếu strategy lỡ trả pandas Series -> convert dict
                    try:
                        import pandas as pd
                        if isinstance(sig, pd.Series):
                            sig = sig.to_dict()
                    except Exception:
                        pass

                    if not isinstance(sig, dict):
                        log.warning("Invalid signal type for %s: %s", symbol, type(sig))
                        continue

                    missing = [k for k in ("side", "price", "atr") if k not in sig]
                    if missing:
                        log.warning("Invalid signal payload for %s (missing %s): %s", symbol, missing, sig)
                        continue

                    side = str(sig["side"]).upper()
                    price = float(sig["price"])
                    atr = float(sig["atr"])

                    symbol_info = get_symbol_info(client, symbol)
                    risk.symbol_step = symbol_info.get("step_size", 0.001)

                    # Position size (LIVE): CHỈ dùng availableBalance để sizing (tránh -2019)
                    avail = _get_available_balance(client)  # USDT available margin
                    if avail <= 0:
                        log.warning("SIZING: availableBalance=0 -> skip %s", symbol)
                        continue
                    balance_usdt = avail * float(cfg.get("max_margin_ratio", 0.95))  # dùng tối đa 95% available

                    # nếu đã có position mở thì không vào thêm, nhưng đảm bảo có TP/SL
                    pos = get_open_position(symbol, client=client)
                    if pos:
                        if not has_protection_orders(symbol, client=client):
                            pos_side = "BUY" if float(pos["amt"]) > 0 else "SELL"
                            qty = abs(float(pos["amt"]))

                            entry = float(pos.get("entryPrice") or 0.0)
                            base_price = entry if entry > 0 else price

                            sl_fix, tp_fix = risk.calc_sl_tp(base_price, atr, pos_side)

                            log.warning(
                                "OPEN POSITION but missing TP/SL => placing protection: %s %s qty=%.6f entry=%.4f SL=%.4f TP=%.4f",
                                pos_side, symbol, qty, base_price, sl_fix, tp_fix
                            )

                            try:
                                place_tp_sl(symbol, pos_side, qty, sl_fix, tp_fix, client=client, cancel_existing=False)
                            except Exception as e:
                                log.warning("Failed to heal TP/SL for %s: %s", symbol, e)

                        log.info("Skip %s: already has open position.", symbol)
                        continue

                    # --- tới đây chắc chắn KHÔNG có position -> mới tính pos_size ---
                    # calc_position_size signature: (balance, price, atr)
                    # balance_usdt là phần margin bạn cho phép dùng
                    pos_size = risk.calc_position_size(balance_usdt, price, atr)
                    if not pos_size or pos_size <= 0:
                        log.warning("SIZING: pos_size=0 -> skip %s", symbol)
                        continue
                    # Check available margin để tránh -2019 (giờ pos_size đã có)
                    notional = pos_size * price
                    required_margin = notional / max(float(leverage), 1.0)

                    if avail > 0 and required_margin > avail * max_margin_ratio:
                        log.warning(
                            "Skip %s: insufficient availableBalance. required~%.4f USDT, available=%.4f USDT (lev=%s).",
                            symbol, required_margin, avail, leverage
                        )
                        continue

                    order = _safe_place_market_order(place_market_order, client, symbol, side, pos_size, min_notional)
                    if not order:
                        log.warning("Order failed/empty for %s", symbol)
                        continue

                    entry_price = float(order.get("_entry_price") or order.get("avgPrice") or 0.0)
                    if entry_price <= 0:
                        entry_price = float(price or 0.0)

                    log.info(
                        "ORDER SENT: %s %s %.6f | entry=%.8f | id=%s | status=%s",
                        side, symbol, pos_size, entry_price, order.get("orderId"), order.get("status")
                    )

                    # Ghi trades.csv trước
                    log_trade({
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry_price,
                        "quantity": float(order.get("_qty") or pos_size),
                        "atr": atr,
                        "strategy": sig.get("strategy", ""),
                        "orderId": order.get("orderId"),
                        "status": order.get("status"),
                    })
                    # Auto đặt TP/SL ngay sau khi order + log_trade xong
                    try:
                        q = float(order.get("_qty") or pos_size)

                        # side ở đây là side của ENTRY (BUY/SELL)
                        sl, tp = risk.calc_sl_tp(entry_price, atr, side)

                        place_tp_sl(
                            symbol=symbol,
                            side=side,
                            quantity=q,
                            sl_price=sl,
                            tp_price=tp,
                            client=client,
                            cancel_existing=False,
                        )
                    except Exception as e:
                        log.warning("Failed to place TP/SL for %s: %s", symbol, e)
                except Exception as e:
                    log.exception("Error processing %s: %s", symbol, e)
            time.sleep(scan_interval)

    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
    except Exception as e:
        log.exception("Unhandled exception: %s", e)
    finally:
        log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
