#!/usr/bin/env python3
# Skeleton risk manager
import logging

log = logging.getLogger("risk-skeleton")

def load_risk_parameters():
    return {
        "leverage": 5,
        "risk_per_trade_percent": 1.5,
        "max_trades_per_day": 6,
        "min_trades_per_day": 2,
    }
