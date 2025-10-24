from binance.client import Client
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import requests

# === CONFIGURATION ===
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
RSI_PERIOD = 6
RSI_THRESHOLDS = [70, 80]
TIMEFRAMES = {
    "1h": Client.KLINE_INTERVAL_1HOUR,
    "15m": Client.KLINE_INTERVAL_15MINUTE
}
SCAN_INTERVAL = 300  # 5 minutes

# === TELEGRAM ALERT SETTINGS ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Send a Telegram alert message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set — skipping alert.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"Telegram alert failed: {e}")

# === CONNECT TO BINANCE ===
client = Client(API_KEY, API_SECRET)

def calculate_rsi(data, period=6):
    delta = data["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

print("Fetching actively traded USDT futures symbols...")
futures_info = client.futures_exchange_info()
futures_symbols = {
    s["symbol"] for s in futures_info["symbols"]
    if s["symbol"].endswith("USDT") and s["status"] == "TRADING"
}
print(f"Found {len(futures_symbols)} actively trading symbols.\n")

# === MAIN LOOP ===
while True:
    print(f"\n=== Scan started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    try:
        tickers = client.futures_ticker()
        price_changes = {
            t["symbol"]: float(t["priceChangePercent"])
            for t in tickers if t["symbol"] in futures_symbols
        }
        top_gainers = sorted(price_changes, key=price_changes.get, reverse=True)[:30]
        results = []

        for symbol in top_gainers:
            for tf_name, tf_interval in TIMEFRAMES.items():
                try:
                    klines = client.get_klines(symbol=symbol, interval=tf_interval, limit=100)
                    df = pd.DataFrame(klines, columns=[
                        "timestamp", "open", "high", "low", "close", "volume",
                        "_1", "_2", "_3", "_4", "_5", "_6"
                    ])
                    df["close"] = df["close"].astype(float)
                    df["RSI_6"] = calculate_rsi(df)
                    last_rsi = df["RSI_6"].iloc[-1]

                    for threshold in RSI_THRESHOLDS:
                        if last_rsi > threshold:
                            msg = f"🔥 {symbol} ({tf_name}) RSI(6) = {last_rsi:.2f} > {threshold}"
                            print(msg)
                            send_telegram_alert(msg)
                            results.append((symbol, tf_name, last_rsi, threshold))

                except Exception as e:
                    print(f"Error fetching {symbol} ({tf_name}): {e}")
                    continue
            time.sleep(0.2)

        if not results:
            print("No coins found with RSI(6) > 95 or 97 at this time.")

    except Exception as e:
        print(f"⚠️ Error during scan: {e}")

    print(f"Sleeping {SCAN_INTERVAL/60:.0f} min...\n")
    time.sleep(SCAN_INTERVAL)
