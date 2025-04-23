#!/usr/bin/env python3
"""
test_stoploss.py

This script automatically retrieves open trades from OANDA,
selects the first available trade, and tests the dynamic stoploss update functionality.
It does the following:
  1. Retrieves open trades and uses the first trade's details.
  2. Determines if the trade is long or short (based on "initialUnits").
  3. Sets an initial stoploss order at -50 pips (for long) or +50 pips (for short) from the entry price.
  4. Waits 20 seconds.
  5. Updates the stoploss order to -25 pips (for long) or +25 pips (for short) from the entry price.
  
Test this on a demo account to verify that the stoploss orders are created/updated as expected.
"""

import time
import logging
import os
import requests
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.endpoints.trades import TradesList
from colorama import init, Fore, Style

# Initialize colorama.
init(autoreset=True)

# Load environment variables.
load_dotenv()

# Retrieve configuration values.
from config import ACCOUNT_ID, API_KEY, BASE_URL

# Initialize the OANDA API client.
api = API(access_token=API_KEY, environment="practice")

def get_open_trades():
    """
    Retrieves open trades from OANDA using the TradesList endpoint.
    Returns a list of trades.
    """
    r = TradesList(accountID=ACCOUNT_ID)
    try:
        api.request(r)
        trades = r.response.get("trades", [])
        return trades
    except Exception as e:
        logging.error(Fore.RED + f"[Test] Exception fetching open trades: {e}")
        return []

def get_pip_size(instrument):
    """
    Returns the pip size for the instrument.
    Typically, 0.0001 for most pairs or 0.01 for instruments with JPY.
    """
    if "JPY" in instrument.upper():
        return 0.01
    else:
        return 0.0001

def update_trade_stop_loss(trade_id, new_stop_loss):
    """
    Updates the stoploss order for a given trade using a cancel-and-recreate approach.
    
    Steps:
      1. Retrieve trade details from OANDA.
      2. If a stoploss order exists, cancel it using its order ID.
         If the cancel response returns a 404, log a warning and proceed.
      3. Create a new stoploss order with the new_stop_loss price (formatted to 5 decimals).
      
    Returns True if successful, otherwise False.
    
    NOTE: Verify that the endpoints and payload format match the current OANDA v20 API.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Step 1: Retrieve trade details.
    trade_url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/trades/{trade_id}"
    try:
        trade_response = requests.get(trade_url, headers=headers)
        if trade_response.status_code != 200:
            logging.error(Fore.RED + f"[Test] Failed to retrieve trade details for {trade_id}. Status code: {trade_response.status_code}")
            return False
        trade_data = trade_response.json().get("trade", {})
    except Exception as e:
        logging.error(Fore.RED + f"[Test] Exception retrieving trade details for {trade_id}: {e}")
        return False

    stoploss_order_id = None
    if "stopLossOrder" in trade_data and trade_data["stopLossOrder"]:
        stoploss_order_id = trade_data["stopLossOrder"].get("id")
    
    # Step 2: Cancel existing stoploss order if found.
    if stoploss_order_id:
        cancel_url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders/{stoploss_order_id}/cancel"
        try:
            cancel_response = requests.put(cancel_url, headers=headers, json={})
            if cancel_response.status_code in (200, 201):
                logging.info(Fore.GREEN + f"[Test] Canceled existing stoploss order {stoploss_order_id} for trade {trade_id}.")
            elif cancel_response.status_code == 404:
                logging.warning(Fore.YELLOW + f"[Test] Stoploss order {stoploss_order_id} not found (404). Proceeding to create new order.")
            else:
                logging.error(Fore.RED + f"[Test] Failed to cancel stoploss order {stoploss_order_id} for trade {trade_id}. Status code: {cancel_response.status_code}")
                # Continue to attempt creation of new stoploss order.
        except Exception as e:
            logging.error(Fore.RED + f"[Test] Exception canceling stoploss order {stoploss_order_id} for trade {trade_id}: {e}")
            return False
    else:
        logging.info(Fore.YELLOW + f"[Test] No existing stoploss order found for trade {trade_id}.")
    
    # Step 3: Create a new stoploss order.
    new_order_url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders"
    # Format the new_stop_loss to 5 decimals.
    price_str = format(new_stop_loss, ".5f")
    order_data = {
        "order": {
            "type": "STOP_LOSS",
            "tradeID": trade_id,
            "price": price_str,
            "timeInForce": "GTC"
        }
    }
    try:
        new_order_response = requests.post(new_order_url, headers=headers, json=order_data)
        if new_order_response.status_code in (200, 201):
            logging.info(Fore.GREEN + f"[Test] Created new stoploss order for trade {trade_id} at {price_str}.")
            return True
        else:
            logging.error(Fore.RED + f"[Test] Failed to create new stoploss order for trade {trade_id}. Status code: {new_order_response.status_code}, Response: {new_order_response.text}")
            return False
    except Exception as e:
        logging.error(Fore.RED + f"[Test] Exception creating new stoploss order for trade {trade_id}: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    print("=== Test Stoploss Update Script ===", flush=True)
    
    # Automatically retrieve open trades.
    trades = get_open_trades()
    if not trades:
        print("No open trades found. Exiting test script.", flush=True)
        exit(1)
    
    # Use the first open trade.
    trade = trades[0]
    trade_id = trade.get("id")
    instrument = trade.get("instrument")
    try:
        entry_price = float(trade.get("price"))
    except (TypeError, ValueError):
        print("Invalid entry price in trade data. Exiting.", flush=True)
        exit(1)
    
    pip_size = get_pip_size(instrument)
    print(f"Automatically selected Trade ID: {trade_id} for Instrument: {instrument}", flush=True)
    print(f"Entry Price: {entry_price}, Pip Size: {pip_size}", flush=True)
    
    # Determine trade direction based on 'initialUnits'.
    # For a short trade, initialUnits usually starts with a '-' character.
    trade_units = trade.get("initialUnits", "0")
    if trade_units.startswith("-"):
        # Short trade: stoploss should be above entry price.
        initial_stoploss = entry_price + (50 * pip_size)
        new_stoploss = entry_price + (25 * pip_size)
    else:
        # Long trade: stoploss should be below entry price.
        initial_stoploss = entry_price - (50 * pip_size)
        new_stoploss = entry_price - (25 * pip_size)
    
    logging.info(Fore.BLUE + f"Setting initial stoploss for trade {trade_id} to {initial_stoploss} ({'-50 pips' if not trade_units.startswith('-') else '+50 pips'}).")
    update_trade_stop_loss(trade_id, initial_stoploss)
    
    logging.info(Fore.BLUE + "Waiting 20 seconds before updating stoploss...")
    time.sleep(20)
    
    logging.info(Fore.BLUE + f"Updating stoploss for trade {trade_id} to {new_stoploss} ({'-25 pips' if not trade_units.startswith('-') else '+25 pips'}).")
    update_trade_stop_loss(trade_id, new_stoploss)
    
    logging.info(Fore.BLUE + "Test complete. Please verify the stoploss orders in your OANDA account.")
