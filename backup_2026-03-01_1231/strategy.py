#!/usr/bin/env python3
"""Strategy module — Scalping + Trend signals using EMA crossover, RSI, ATR, Volume."""
import logging
import pandas as pd  # pandas, numpy, and ta should be installed in venv

log = logging.getLogger("strategy")

# Import necessary functions from market module
try:
    from market import fetch_klines, add_indicators
except ImportError as e:
    log.error("Failed to import market module (%s). Ensure market.py exposes fetch_klines/add_indicators.", e)
    raise

def generate_signal(client, symbol, cfg):
    """
    Analyze a symbol on 5m timeframe and generate trading signal.
    Returns: dict with signal info or None if no signal.
    Signal: {"side": "BUY"|"SELL", "symbol": str, "price": float, "atr": float, "strategy": str}
    """
    try:
        klines_df = fetch_klines(
            client,
            symbol=symbol,
            interval="5m",
            limit=cfg.get("klines_limit", 100),
        )

        if klines_df is None or klines_df.empty or len(klines_df) < 30:
            log.debug("Not enough kline data for %s, skipping signal generation.", symbol)
            return None

        klines_df = add_indicators(
            klines_df,
            ema_fast=cfg.get("ema_fast", 9),
            ema_slow=cfg.get("ema_slow", 21),
            rsi_period=cfg.get("rsi_period", 14),
            atr_period=cfg.get("atr_period", 14),
        )

        last = klines_df.iloc[-1]
        previous = klines_df.iloc[-2]

        ema_fast = last.get("ema_fast")
        ema_slow = last.get("ema_slow")
        rsi = last.get("rsi")
        atr = last.get("atr")
        close = last.get("close")
        volume = last.get("volume")
        volume_sma = last.get("volume_sma")

        if any(pd.isna(x) for x in [ema_fast, ema_slow, rsi, atr, close, volume_sma]):
            log.debug("Indicators have NaN values for %s, skipping signal.", symbol)
            return None

        volume_mult = cfg.get("volume_mult", 1.3)
        if volume_sma > 0 and volume < volume_sma * volume_mult:
            log.debug("Volume filter failed for %s", symbol)
            return None

        rsi_oversold = cfg.get("rsi_oversold", 30)
        rsi_overbought = cfg.get("rsi_overbought", 70)

        signal = None

        if previous["ema_fast"] <= previous["ema_slow"] and ema_fast > ema_slow and rsi < rsi_overbought:
            signal = {"side": "BUY", "symbol": symbol, "price": float(close), "atr": float(atr), "strategy": "trend_scalp_long"}

        elif previous["ema_fast"] >= previous["ema_slow"] and ema_fast < ema_slow and rsi > rsi_oversold:
            signal = {"side": "SELL", "symbol": symbol, "price": float(close), "atr": float(atr), "strategy": "trend_scalp_short"}

        elif previous["rsi"] < rsi_oversold and rsi >= rsi_oversold and ema_fast > ema_slow:
            signal = {"side": "BUY", "symbol": symbol, "price": float(close), "atr": float(atr), "strategy": "rsi_reversal_long"}

        elif previous["rsi"] > rsi_overbought and rsi <= rsi_overbought and ema_fast < ema_slow:
            signal = {"side": "SELL", "symbol": symbol, "price": float(close), "atr": float(atr), "strategy": "rsi_reversal_short"}

        if signal:
            log.info("Generated Signal: %s %s @ %.4f | ATR=%.4f | Strategy=%s",
                     signal["side"], symbol, signal["price"], signal["atr"], signal["strategy"])

        return signal

    except Exception as e:
        log.exception("Error analyzing %s: %s", symbol, e)
        return None
