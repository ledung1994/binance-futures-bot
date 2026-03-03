import os
import logging
from typing import List

class MaskingFilter(logging.Filter):
    """
    Masks secrets in log messages. It replaces any occurrence of the actual
    secret values (from env) with '***'.
    """
    def __init__(self, secret_values: List[str]):
        super().__init__()
        self._secrets = [s for s in secret_values if s]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        new_msg = str(msg)
        for s in self._secrets:
            if s and s in new_msg:
                new_msg = new_msg.replace(s, "***")

        # overwrite message safely
        record.msg = new_msg
        record.args = ()
        return True

def install_log_masking() -> None:
    """
    Install masking filter on the root logger.
    Must be called after dotenv load (so env has secrets).
    """
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    flt = MaskingFilter([api_key, api_secret])

    root = logging.getLogger()
    # Avoid installing twice
    for existing in root.filters:
        if isinstance(existing, MaskingFilter):
            return
    root.addFilter(flt)
