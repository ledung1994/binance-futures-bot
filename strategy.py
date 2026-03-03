#!/usr/bin/env python3
"""
Strategy module — Trend + EMA200 support.
Contract:
- generate_signal(...) returns:
    - None (no trade)
    - dict with keys: side, price, atr, strategy
"""

import logging

log = logging.getLogger("strategy")

from market_data import fetch_klines, add_indicators


def _ensure_ema200(df):
    """Ensure df has ema200 column (compute from close if missing)."""
    if df is None:
        return df
    if "ema200" in df.columns:
        return df
    if "close" not in df.columns:
        raise RuntimeError("Missing 'close' column; cannot compute EMA200")

    try:
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    except Exception as e:
        raise RuntimeError(f"Failed computing EMA200: {e}") from e

    return df


def generate_signal(client, symbol, cfg):
    """
    Returns:
      None -> no signal
      dict -> {"side": "BUY"/"SELL", "price": float, "atr": float, "strategy": str}
    """

    interval = cfg.get("timeframe", cfg.get("interval", "5m"))
    limit = int(cfg.get("klines_limit", cfg.get("limit", 200)))

    # Fetch klines
    df = fetch_klines(client, symbol, interval=interval, limit=limit)
    if df is None or getattr(df, "empty", True) or len(df) < 50:
        log.warning("Not enough kline data for %s", symbol)
        return None

    # Add indicators (ema_fast/ema_slow/rsi/atr)
    df = add_indicators(
        df,
        ema_fast=int(cfg.get("ema_fast", 9)),
        ema_slow=int(cfg.get("ema_slow", 21)),
        rsi_period=int(cfg.get("rsi_period", 14)),
        atr_period=int(cfg.get("atr_period", 14)),
    )

    df = _ensure_ema200(df)
    if df is None or getattr(df, "empty", True):
        return None

    last = df.iloc[-1]

    # Required fields
    close = float(last.get("close", 0.0) or 0.0)
    atr = float(last.get("atr", 0.0) or 0.0)
    ema_fast = float(last.get("ema_fast", 0.0) or 0.0)
    ema_slow = float(last.get("ema_slow", 0.0) or 0.0)
    ema200 = float(last.get("ema200", 0.0) or 0.0)
    rsi = float(last.get("rsi", 50.0) or 50.0)

    if close <= 0 or atr <= 0:
        return None

    # Filters / switches
    use_ema200_filter = bool(cfg.get("use_ema200_filter", True))
    rsi_buy_max = float(cfg.get("rsi_buy_max", 70.0))
    rsi_sell_min = float(cfg.get("rsi_sell_min", 30.0))

    # Trend logic (simple & safe)
    # BUY: fast>slow AND (close>ema200 if enabled) AND rsi not too overbought
    # SELL: fast<slow AND (close<ema200 if enabled) AND rsi not too oversold
    buy_ok = ema_fast > ema_slow and (not use_ema200_filter or close > ema200) and (rsi <= rsi_buy_max)
    sell_ok = ema_fast < ema_slow and (not use_ema200_filter or close < ema200) and (rsi >= rsi_sell_min)

    if buy_ok:
        return {
            "side": "BUY",
            "price": close,
            "atr": atr,
            "strategy": "trend_ema_fast_slow + ema200 + rsi",
        }

    if sell_ok:
        return {
            "side": "SELL",
            "price": close,
            "atr": atr,
            "strategy": "trend_ema_fast_slow + ema200 + rsi",
        }

    return None
