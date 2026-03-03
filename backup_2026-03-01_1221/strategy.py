#!/usr/bin/env python3
"""Strategy module — Scalping + Trend signals using EMA crossover, RSI, ATR, Volume."""
import logging
from market import fetch_klines, add_indicators

log = logging.getLogger("strategy")

def analyze_symbol(client, symbol, cfg):
    """
    Analyze a symbol on 5m timeframe.
    Returns: dict with signal info or None if no signal.
    Signal: {"side": "BUY"|"SELL", "symbol": str, "price": float, "atr": float, "strategy": str}
    """
    try:
        df = fetch_klines(client, symbol=symbol, interval="5m", limit=100)
        if df.empty or len(df) < 30:
            return None

        df = add_indicators(
            df,
            ema_fast=cfg.get("ema_fast", 9),
            ema_slow=cfg.get("ema_slow", 21),
            rsi_period=cfg.get("rsi_period", 14),
            atr_period=cfg.get("atr_period", 14),
        )

        last = df.iloc[-1]
        prev = df.iloc[-2]

        ema_fast = last["ema_fast"]
        ema_slow = last["ema_slow"]
        rsi = last["rsi"]
        atr = last["atr"]
        close = last["close"]
        volume = last["volume"]
        vol_sma = last["volume_sma"]

        if any(x is None or x != x for x in [ema_fast, ema_slow, rsi, atr, vol_sma]):
            return None

        # Volume filter: volume must be above average
        volume_mult = cfg.get("volume_mult", 1.3)
        if vol_sma > 0 and volume < vol_sma * volume_mult:
            return None

        rsi_oversold = cfg.get("rsi_oversold", 30)
        rsi_overbought = cfg.get("rsi_overbought", 70)

        signal = None

        # --- TREND + SCALPING LONG ---
        # EMA fast crosses above EMA slow (bullish crossover)
        # RSI not overbought
        if prev["ema_fast"] <= prev["ema_slow"] and ema_fast > ema_slow and rsi < rsi_overbought:
            signal = {
                "side": "BUY",
                "symbol": symbol,
                "price": close,
                "atr": atr,
                "strategy": "trend_scalp_long",
            }

        # --- TREND + SCALPING SHORT ---
        # EMA fast crosses below EMA slow (bearish crossover)
        # RSI not oversold
        elif prev["ema_fast"] >= prev["ema_slow"] and ema_fast < ema_slow and rsi > rsi_oversold:
            signal = {
                "side": "SELL",
                "symbol": symbol,
                "price": close,
                "atr": atr,
                "strategy": "trend_scalp_short",
            }

        # --- RSI REVERSAL LONG (scalping) ---
        elif prev["rsi"] < rsi_oversold and rsi >= rsi_oversold and ema_fast > ema_slow:
            signal = {
                "side": "BUY",
                "symbol": symbol,
                "price": close,
                "atr": atr,
                "strategy": "rsi_reversal_long",
            }

        # --- RSI REVERSAL SHORT (scalping) ---
        elif prev["rsi"] > rsi_overbought and rsi <= rsi_overbought and ema_fast < ema_slow:
            signal = {
                "side": "SELL",
                "symbol": symbol,
                "price": close,
                "atr": atr,
                "strategy": "rsi_reversal_short",
            }

        if signal:
            log.info("Signal: %s %s @ %.4f | ATR=%.4f | Strategy=%s",
                     signal["side"], symbol, close, atr, signal["strategy"])

        return signal

    except Exception as e:
        log.exception("Error analyzing %s: %s", symbol, e)
        return None
