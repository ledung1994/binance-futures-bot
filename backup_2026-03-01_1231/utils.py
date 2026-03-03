"""Utilities: logging, config, trade CSV logger."""
import os
import csv
import yaml
import logging
from datetime import datetime, timezone

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name="bot", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        fh = logging.FileHandler(os.path.join(LOG_DIR, f"{name}.log"))
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

log = setup_logger()

def load_config():
    cfg_path = os.path.join(BOT_DIR, "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    # ENV overrides
    cfg["api_key"] = os.environ.get("BINANCE_API_KEY", cfg.get("api_key", ""))
    cfg["api_secret"] = os.environ.get("BINANCE_API_SECRET", cfg.get("api_secret", ""))
    cfg["use_testnet"] = os.environ.get("BINANCE_USE_TESTNET", str(cfg.get("use_testnet", "false"))).lower() == "true"
    cfg["leverage"] = int(os.environ.get("BINANCE_LEVERAGE", cfg.get("leverage", 5)))
    cfg["kill_switch_enabled"] = os.environ.get("BINANCE_KILL_SWITCH", str(cfg.get("kill_switch_enabled", "true"))).lower() == "true"
    cfg.setdefault("risk_per_trade_percent", 1.5)
    cfg.setdefault("max_trades_per_day", 6)
    cfg.setdefault("min_trades_per_day", 2)
    cfg.setdefault("max_daily_loss_percent", 5.0)
    cfg.setdefault("atr_period", 14)
    cfg.setdefault("atr_sl_multiplier", 1.5)
    cfg.setdefault("atr_tp_multiplier", 2.0)
    cfg.setdefault("trailing_stop_atr_mult", 1.0)
    cfg.setdefault("cooldown_seconds", 120)
    cfg.setdefault("scan_interval_seconds", 30)
    cfg.setdefault("timeframes", ["1m", "5m", "1h"])
    cfg.setdefault("top_volume_count", 20)
    cfg.setdefault("ema_fast", 9)
    cfg.setdefault("ema_slow", 21)
    cfg.setdefault("rsi_period", 14)
    cfg.setdefault("rsi_overbought", 70)
    cfg.setdefault("rsi_oversold", 30)
    cfg.setdefault("volume_mult", 1.5)
    return cfg

def log_trade(data: dict):
    """Append trade to CSV."""
    csv_path = os.path.join(LOG_DIR, "trades.csv")
    exists = os.path.exists(csv_path)
    fields = ["timestamp", "symbol", "side", "entry_price", "quantity",
              "sl_price", "tp_price", "leverage", "strategy", "status", "pnl", "note"]
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not exists:
            w.writeheader()
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        w.writerow(data)

def now_utc():
    return datetime.now(timezone.utc)
