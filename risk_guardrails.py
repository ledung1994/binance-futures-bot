import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("bot.risk")

@dataclass
class RiskGuardrails:
    max_drawdown_pct: float = 2.0
    max_position_pct: float = 1.0  # % balance
    initial_balance: Optional[float] = None
    circuit_breaker_active: bool = False

    def update_initial_balance(self, balance: float) -> None:
        if self.initial_balance is None and balance is not None:
            self.initial_balance = float(balance)

    def should_halt(self, drawdown_pct: float, position_notional: float, balance: float) -> bool:
        if balance is None:
            logger.warning("Balance is None; skip guardrails.")
            return False

        self.update_initial_balance(balance)

        if float(drawdown_pct) >= float(self.max_drawdown_pct):
            self.circuit_breaker_active = True
            logger.warning(
                "CIRCUIT BREAKER: drawdown %.4f%% >= %.4f%%",
                float(drawdown_pct), float(self.max_drawdown_pct)
            )

        denom = max(1e-6, float(balance))
        pos_pct = (float(position_notional) / denom) * 100.0
        if pos_pct > float(self.max_position_pct):
            self.circuit_breaker_active = True
            logger.warning(
                "CIRCUIT BREAKER: position %.4f%% > %.4f%% (notional=%.4f balance=%.4f)",
                pos_pct, float(self.max_position_pct), float(position_notional), float(balance)
            )

        return self.circuit_breaker_active
