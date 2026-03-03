#!/usr/bin/env python3
import logging
from datetime import datetime, timezone

log = logging.getLogger("risk")


class RiskManager:
    def __init__(self, cfg):
        self.leverage = cfg.get("leverage", 5)
        self.risk_per_trade_percent = cfg.get("risk_per_trade_percent", 1.0)
        self.atr_sl_multiplier = cfg.get("atr_sl_multiplier", 1.5)
        self.atr_tp_multiplier = cfg.get("atr_tp_multiplier", 2.0)
        self.min_notional = cfg.get("min_notional", 5.0)
        self.cooldown_seconds = cfg.get("cooldown_seconds", 120)

        self.trades_today = 0
        self.initial_balance = 0.0
        self.killed = False
        self.symbol_step = None

    def calc_position_size(self, balance, price, atr):
        if atr <= 0 or price <= 0 or balance <= 0:
            return 0.0

        # 1️⃣ Số tiền chấp nhận rủi ro cho 1 lệnh
        risk_amount_usd = balance * (self.risk_per_trade_percent / 100.0)

        # 2️⃣ Khoảng cách SL
        sl_dist = atr * self.atr_sl_multiplier
        if sl_dist <= 0:
            return 0.0

        # 3️⃣ Size theo risk model
        qty_by_risk = risk_amount_usd / sl_dist

        # 4️⃣ Giới hạn theo margin & leverage
        max_qty_by_margin = (balance * self.leverage) / price

        qty = min(qty_by_risk, max_qty_by_margin)

        # 5️⃣ Ép đạt min_notional nếu có thể (tránh Notional too small)
        min_qty_by_notional = self.min_notional / price

        if qty * price < self.min_notional:
            # nếu có đủ margin để đạt min_notional thì nâng lên
            if min_qty_by_notional <= max_qty_by_margin:
                qty = min_qty_by_notional
            else:
                return 0.0  # không đủ margin để trade tối thiểu

        return max(qty, 0.0)

    def calc_sl_tp(self, price, atr, side):
        if atr <= 0:
            return price, price

        if side == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        return sl, tp
