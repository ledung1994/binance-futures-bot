#!/usr/bin/env python3
"""Strategy module — enhanced: Trend + EMA200 support."""
import logging
import pandas as pd
import numpy as np
try:
from market import fetch_klines, add_indicators
except ImportError:
pass

log = logging.getLogger("strategy")

def _ensure_ema200(df):
if "ema_200" not in df.columns:
df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
return df

def generate_signal(client, symbol, cfg):
try:
klines_df = fetch_klines(client, symbol=symbol, interval="5m",
limit=cfg.get("klines_limit", 100))
min_klines_needed = cfg.get("min_klines_for_indicators", 30)
if klines_df is None or klines_df.empty or len(klines_df) < min_klines_needed:
log.debug(f"Not enough kline data ({len(klines_df)} bars) for {symbol}, skipping.")
return None

    df = add_indicators(klines_df,
                        ema_fast=cfg.get("ema_fast", 9),
                        ema_slow=cfg.get("ema_slow", 21),
                        rsi_period=cfg.get("rsi_period", 14),
                        atr_period=cfg.get("atr_period", 14))
    df = _ensure_ema200(df)
    last = df.iloc[-1]
    previous = df.iloc[-2]
    ema_fast = last["ema_fast"]
    ema_slow = last["ema_slow"]
    ema_200 = last["ema_200"]
    rsi = last["rsi"]
    atr = last["atr"]
    close = last["close"]

    if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi) or pd.isna(atr) or close <= 0:
        return None

    signal = None
    if previous["ema_fast"] <= previous["ema_slow"] and ema_fast > ema_slow and rsi < 80 and close > ema_200:
        signal = {"side": "BUY", "symbol": symbol, "price": close, "atr": atr, "strategy": "trend_scalp_long"}
    elif previous["ema_fast"] >= previous["ema_slow"] and ema_fast < ema_slow and rsi > 20 and close < ema_200:
        signal = {"side": "SELL", "symbol": symbol, "price": close, "atr": atr, "strategy": "trend_scalp_short"}
    if signal:
        log.info("Generated Signal: %s %s @ %.4f | ATR=%.4f | Strategy=%s", signal["side"], symbol, close, atr, signal["strategy"])
    return signal
except Exception as e:
    log.exception("Error analyzing %s: %s", symbol, e)
    return None
