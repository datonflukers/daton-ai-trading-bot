import os
import datetime
import pandas as pd
import requests
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# --- Environment Setup ---
OANDA_MODE = os.getenv("OANDA_MODE", "paper").lower()
if OANDA_MODE == "live":
    BASE_URL = "https://api-fxtrade.oanda.com/v3"
    ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID_LIVE")
    OANDA_API_KEY = os.getenv("OANDA_API_KEY_LIVE")
else:
    BASE_URL = "https://api-fxpractice.oanda.com/v3"
    ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID_PAPER")
    OANDA_API_KEY = os.getenv("OANDA_API_KEY_PAPER")

headers = {
    "Authorization": f"Bearer {OANDA_API_KEY}",
    "Content-Type": "application/json"
}

def get_candles(instrument, granularity="M15", count=100):
    """
    Retrieves historical candle data from OANDA for the given instrument.

    Args:
        instrument (str): Instrument identifier (e.g., "EUR_USD").
        granularity (str): Time interval for the candles (e.g., "M15" for 15 minutes).
        count (int): Number of candles to retrieve.

    Returns:
        tuple: (pandas.DataFrame, list of records)
    """
    url = f"{BASE_URL}/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "count": count,
        "price": "M"  # Using midpoint pricing
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print("Error fetching candles for", instrument, response.text)
        return None, []
    data = response.json()
    candles = data.get("candles", [])
    records = []
    for candle in candles:
        if candle.get("complete", False):
            record = {
                "time": candle["time"],
                "open": float(candle["mid"]["o"]),
                "high": float(candle["mid"]["h"]),
                "low": float(candle["mid"]["l"]),
                "close": float(candle["mid"]["c"]),
                "volume": candle["volume"]
            }
            records.append(record)
    df = pd.DataFrame(records)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
    return df, records

if __name__ == "__main__":
    instrument = "EUR_USD"  # Change to your desired instrument if needed
    df, records = get_candles(instrument, granularity="M15", count=100)

    if df is not None and not df.empty:
        print("Columns in DataFrame:")
        print(df.columns)
        print("\nData Types:")
        print(df.dtypes)
        print("\nFirst few rows:")
        print(df.head())
    else:
        print("No data retrieved.")
