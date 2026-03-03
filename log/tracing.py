import logging

def log_signal(signal, symbol):
# Ghi log tín hiệu
logging.getLogger("bot").info("Signal: %s %s @ %.6f", signal.get("side"), symbol, signal.get("price", 0))
return True

def log_trade_event(event):
# Ghi log giao dịch (signal + order)
logging.getLogger("order").info("TradeEvent: %s", event)
return True
