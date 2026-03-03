import os
from binance.client import Client

api_key = os.environ.get("BINANCE_API_KEY")
api_secret = os.environ.get("BINANCE_API_SECRET")

if not api_key or not api_secret:
    print("ERROR: BINANCE_API_KEY và BINANCE_API_SECRET phải được thiết lập trong môi trường.")
    raise SystemExit(1)

use_testnet = os.environ.get("BINANCE_USE_TESTNET", "false").lower() == "true"

client = Client(api_key, api_secret)

# Nếu bạn dùng Futures TESTNET, python-binance cần trỏ đúng endpoint futures testnet
if use_testnet:
    client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"

try:
    acc = client.futures_account()
    print("Connect OK.")
    print("totalWalletBalance =", acc.get("totalWalletBalance", "n/a"))
    print("availableBalance   =", acc.get("availableBalance", "n/a"))
except Exception as e:
    print("Connection/Test failed:", repr(e))
    raise
