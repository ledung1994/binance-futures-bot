#!/usr/bin/env python3
"""Strategy module — enhanced: Trend + EMA200 support."""
import logging

log = logging.getLogger("strategy")

# NOTE:
# File này giả định project của bạn đã có:
# - fetch_klines_df(client, symbol, interval, limit)
# - add_indicators(df, ema_fast, ema_slow, rsi_period, atr_period)
# Nếu tên hàm khác, bạn đổi lại cho khớp.
from indicators import add_indicators
from data import fetch_klines_df


def _ensure_ema200(df):
    """
    Đảm bảo df có cột ema200. Nếu add_indicators chưa tạo, tự tính từ close.
    """
    if "ema200" in df.columns:
        return df
    if "close" not in df.columns:
        raise RuntimeError("Missing 'close' column; cannot compute EMA200")

    # pandas ewm
    try:
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    except Exception as e:
        raise RuntimeError(f"Failed computing EMA200: {e}") from e

    return df


def generate_signal(client, symbol, cfg):
    """
    Trả về dict/Series last candle đã có indicators.
    Bot hiện tại của bạn có thể đang dùng last['signal'] hoặc logic riêng.
    Patch này chủ yếu đảm bảo ATR/EMA200 có sẵn để trade_live đặt TP/SL.
    """
    interval = cfg.get("interval", "5m")
    limit = int(cfg.get("limit", 200))

    klines_df = fetch_klines_df(client, symbol, interval=interval, limit=limit)
    if klines_df is None or len(klines_df) < 50:
        raise RuntimeError(f"Not enough kline data for {symbol}")

    df = add_indicators(
        klines_df,
        ema_fast=cfg.get("ema_fast", 9),
        ema_slow=cfg.get("ema_slow", 21),
        rsi_period=cfg.get("rsi_period", 14),
        atr_period=cfg.get("atr_period", 14),
    )

    df = _ensure_ema200(df)
    last = df.iloc[-1]

    # ATR cần > 0 để đặt TP/SL
    atr = float(last.get("atr") or 0.0)
    if atr <= 0:
        raise RuntimeError(f"ATR invalid for {symbol}: {atr}")

    return last
