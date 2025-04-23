"""
Risk Management Module Using SQLite Trade Data

This module retrieves live trade data from an SQLite database that is updated by trade_profit_monitor.py.
It then calculates profit in pips (based on entry and current prices), and:
  - Closes trades via a fixed take-profit rule if profit reaches TAKE_PROFIT_TARGET_PIPS.
  - Otherwise, if profit exceeds a trailing activation threshold (PROFIT_THRESHOLD_PIPS),
    it dynamically updates the stoploss order to trail the best price (with a buffer of TRAILING_BUFFER_PIPS).
It prints detailed information about each trade decision including whether closing the trade was successful.
Ensure that your .env file is correctly configured with:
    OANDA_ACCOUNT_ID_PAPER, OANDA_API_KEY_PAPER, and DATA_FOLDER.
"""

import os
import time
import datetime
import sqlite3
import json
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.trades as trades_endpoints
import oandapyV20.endpoints.pricing as pricing_endpoints

# Load environment variables
load_dotenv()

# Retrieve credentials and configuration
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID_PAPER")
API_KEY = os.getenv("OANDA_API_KEY_PAPER")
DATA_FOLDER = os.getenv("DATA_FOLDER", ".")   # default to current directory if not set

# SQLite DB file (must be the same file that trade_profit_monitor.py uses)
DB_FILE = os.path.join(DATA_FOLDER, "trade_info.db")

# Initialize the OANDA API client
client = API(access_token=API_KEY)

# --- Configuration Constants ---
TAKE_PROFIT_TARGET_PIPS = 50       # Fixed take-profit target in pips
PROFIT_THRESHOLD_PIPS = 20         # Profit (in pips) at which trailing stoploss updates begin
TRAILING_BUFFER_PIPS = 5           # Buffer (in pips) for trailing stoploss
MONITOR_INTERVAL_SECONDS = 60      # Check the database every 60 seconds

### SQLite Data Retrieval Function ###

def load_trade_info_from_db():
    """
    Loads the current trade data from the SQLite database.
    Assumes the table 'trade_info' (populated by trade_profit_monitor.py) has these columns:
      trade_id, instrument, entry_price, current_price,
      unrealized_pl_usd, calculated_profit_pips, timestamp.
    Returns a list of dictionaries (one per open trade).
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_info")
        rows = cursor.fetchall()
        conn.close()
        trade_data = [dict(row) for row in rows]
        return trade_data
    except Exception as e:
        print(f"Error loading trade info from database: {e}")
        return []

### OANDA API Functions ###

def get_pip_size(instrument):
    """
    Returns the pip size for an instrument:
      - For most pairs: 0.0001, for JPY pairs: 0.01.
    """
    return 0.01 if "JPY" in instrument.upper() else 0.0001

def get_current_price(instrument):
    """
    Retrieve the current mid-price using the PricingInfo endpoint.
    """
    params = {"instruments": instrument}
    r = pricing_endpoints.PricingInfo(accountID=ACCOUNT_ID, params=params)
    client.request(r)
    data = r.response
    if "prices" in data and data["prices"]:
        price_info = data["prices"][0]
        try:
            bid = float(price_info["bids"][0]["price"])
            ask = float(price_info["asks"][0]["price"])
            return (bid + ask) / 2
        except Exception as e:
            print(f"Error parsing price data for {instrument}: {e}")
            return None
    else:
        print(f"Failed to retrieve price for {instrument}")
        return None

def close_trade(trade_id, instrument):
    """
    Closes an open trade using a market order via OANDA's TradeClose endpoint.
    Prints whether the trade closure was successful.
    """
    payload = {"units": "ALL"}
    r = trades_endpoints.TradeClose(accountID=ACCOUNT_ID, tradeID=trade_id, data=payload)
    client.request(r)
    if r.response:
        print(f"{datetime.datetime.now()} - Successfully closed trade {trade_id} for {instrument}")
    else:
        print(f"{datetime.datetime.now()} - Failed to close trade {trade_id} for {instrument}")

def update_trade_stop_loss(trade_id, instrument, new_stop_loss):
    """
    Updates the stoploss order for a trade dynamically.
    This function sends a modification request to update the stoploss.
    Attempts to use TradeClientExtensionsModify (or fallback to TradeCRCD if necessary).
    """
    data = {
        "stopLoss": {
            "price": f"{round_price(instrument, new_stop_loss):.5f}"
        }
    }
    try:
        from oandapyV20.endpoints.trades import TradeClientExtensionsModify
    except ImportError:
        from oandapyV20.endpoints.trades import TradeCRCD as TradeClientExtensionsModify
    r = TradeClientExtensionsModify(accountID=ACCOUNT_ID, tradeID=trade_id, data=data)
    client.request(r)
    if r.response:
        print(f"{datetime.datetime.now()} - Updated stoploss for trade {trade_id} to {round_price(instrument, new_stop_loss)}")
    else:
        print(f"{datetime.datetime.now()} - Failed to update stoploss for trade {trade_id}")

### Monitoring Function Using SQLite Data ###

def monitor_trades_from_db():
    """
    Continuously monitors trade data loaded from the SQLite database.
    For each trade:
      - Reads the entry price, current price, and calculated profit (in pips).
      - If the profit in pips >= TAKE_PROFIT_TARGET_PIPS, closes the trade (take profit).
      - Else if profit in pips >= PROFIT_THRESHOLD_PIPS, updates the stoploss order dynamically to trail the best price.
      - Prints detailed logs including whether the trade was closed successfully.
    """
    best_prices_db = {}  # In-memory dictionary to track the best price reached per trade_id

    while True:
        print(f"\n--- Monitoring Cycle Started at {datetime.datetime.now()} ---")
        trade_data = load_trade_info_from_db()
        for trade in trade_data:
            trade_id = trade["trade_id"]
            instrument = trade["instrument"]
            entry_price = trade["entry_price"]
            current_price = trade["current_price"]
            profit_pips = trade["calculated_profit_pips"]

            print(f"Trade {trade_id} ({instrument}) - Calculated Profit: {profit_pips:.2f} pips; Current Price: {current_price}")

            # Determine direction based on profit (assuming profit_pips positive = long, negative = short)
            direction = "long" if profit_pips >= 0 else "short"

            # Check fixed take profit condition
            if direction == "long" and profit_pips >= TAKE_PROFIT_TARGET_PIPS:
                print(f"Long trade {trade_id} reached take profit target ({TAKE_PROFIT_TARGET_PIPS} pips). Closing trade.")
                close_trade(trade_id, instrument)
                if trade_id in best_prices_db:
                    del best_prices_db[trade_id]
                continue
            if direction == "short" and profit_pips >= TAKE_PROFIT_TARGET_PIPS:
                print(f"Short trade {trade_id} reached take profit target ({TAKE_PROFIT_TARGET_PIPS} pips). Closing trade.")
                close_trade(trade_id, instrument)
                if trade_id in best_prices_db:
                    del best_prices_db[trade_id]
                continue

            # Check if profit is high enough to start trailing updates
            if profit_pips >= PROFIT_THRESHOLD_PIPS:
                # Update best price for this trade
                if trade_id not in best_prices_db:
                    best_prices_db[trade_id] = current_price
                else:
                    if direction == "long" and current_price > best_prices_db[trade_id]:
                        best_prices_db[trade_id] = current_price
                    elif direction == "short" and current_price < best_prices_db[trade_id]:
                        best_prices_db[trade_id] = current_price

                # Calculate the new dynamic stoploss level
                if direction == "long":
                    new_stoploss = best_prices_db[trade_id] - (TRAILING_BUFFER_PIPS * get_pip_size(instrument))
                    print(f"Trade {trade_id} ({instrument}) - Best Price: {best_prices_db[trade_id]:.5f}; New Trailing Stoploss: {round_price(instrument, new_stoploss)}")
                    update_trade_stop_loss(trade_id, instrument, new_stoploss)
                else:
                    new_stoploss = best_prices_db[trade_id] + (TRAILING_BUFFER_PIPS * get_pip_size(instrument))
                    print(f"Trade {trade_id} ({instrument}) - Best Price: {best_prices_db[trade_id]:.5f}; New Trailing Stoploss: {round_price(instrument, new_stoploss)}")
                    update_trade_stop_loss(trade_id, instrument, new_stoploss)
        print(f"--- Monitoring Cycle Ended at {datetime.datetime.now()} ---\n")
        time.sleep(MONITOR_INTERVAL_SECONDS)

### RiskManager Class (Additional Functions Remain Unchanged) ###

class RiskManager:
    def __init__(self):
        self.consecutive_stoploss_count = 0
        self.risk_score = 0

    def record_trade_event(self, event):
        if event == "take_profit_hit":
            self.risk_score += 5
            self.consecutive_stoploss_count = 0
        elif event == "stoploss_hit":
            self.risk_score -= 2
            self.consecutive_stoploss_count += 1
            if self.consecutive_stoploss_count >= 3:
                self.risk_score -= 5
        print(f"[Risk Manager] Updated risk score: {self.risk_score}")

    def get_risk_summary(self):
        return f"Current Risk Score: {self.risk_score}, Consecutive Stoploss Count: {self.consecutive_stoploss_count}"

    # (Other methods like process_signal() and best trade selection remain if needed)

### Main Execution ###

if __name__ == "__main__":
    print("Starting Risk Management Monitoring (using SQLite trade info)...")
    monitor_trades_from_db()
