#!/usr/bin/env python3
"""Market data module — fetches real kline data from Binance Futures."""
import time
import logging
import pandas as pd
import numpy as np
from binance.client import Client

log = logging.getLogger("market")

def get_client():
    """Get or create Binance client from environment."""
    import os
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    return Client(api_key, api_secret)

def fetch_klines(client, symbol="BTCUSDT", interval="5m", limit=100):
    """Fetch kline/candlestick data and return as DataFrame."""
    try:
        raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        return df
    except Exception as e:
        log.exception("Failed to fetch klines for %s %s: %s", symbol, interval, e)
        return pd.DataFrame()

def fetch_price(client, symbol="BTCUSDT"):
    """Fetch current mark price for a futures symbol."""
    try:
        ticker = client.futures_mark_price(symbol=symbol)
        return float(ticker["markPrice"])
    except Exception as e:
        log.exception("Failed to fetch price for %s: %s", symbol, e)
        return 0.0

def get_top_volume_symbols(client, top_n=20):
    """Get top N USDT-M futures symbols by 24h quote volume."""
    try:
        tickers = client.futures_ticker()
        usdt_tickers = [t for t in tickers if t["symbol"].endswith("USDT")]
        usdt_tickers.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        return [t["symbol"] for t in usdt_tickers[:top_n]]
    except Exception as e:
        log.exception("Failed to get top volume symbols: %s", e)
        return ["BTCUSDT", "ETHUSDT"]

def calc_ema(series, period):
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_atr(df, period=14):
    """Calculate Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def add_indicators(df, ema_fast=9, ema_slow=21, rsi_period=14, atr_period=14):
    """Add technical indicators to kline DataFrame."""
    if df.empty:
        return df
    df = df.copy()
    df["ema_fast"] = calc_ema(df["close"], ema_fast)
    df["ema_slow"] = calc_ema(df["close"], ema_slow)
    df["rsi"] = calc_rsi(df["close"], rsi_period)
    df["atr"] = calc_atr(df, atr_period)
    df["volume_sma"] = df["volume"].rolling(window=20).mean()
    return df
