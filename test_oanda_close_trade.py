#!/usr/bin/env python3
"""
test_close_all_oanda_trades.py

This script retrieves all open trades from OANDA using the /v3/accounts/{ACCOUNT_ID}/openTrades endpoint
and then attempts to close each one automatically.

It logs detailed status messages and error codes so you can diagnose any issues.
Ensure your .env file (or config.py) has your OANDA credentials and base URL properly configured.
"""

import os
import requests
import logging
from dotenv import load_dotenv
from config import ACCOUNT_ID, API_KEY, BASE_URL

# Load environment variables from the .env file.
load_dotenv()

# Configure logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_open_trades():
    """
    Retrieves all open trades from OANDA.
    
    Returns:
        List of trades if successful; otherwise, None.
    """
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/openTrades"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            logging.info("[POSITION] Successfully retrieved open trades.")
            data = response.json()
            return data.get("trades", [])
        else:
            logging.error(f"[POSITION] Failed to retrieve open trades. Status code: {response.status_code} Response: {response.text}")
            return None
    except Exception as e:
        logging.error(f"[POSITION] Exception while retrieving open trades: {e}")
        return None

def close_trade(trade_id):
    """
    Closes a trade via the OANDA API by sending a PUT request to the trade close endpoint.
    
    Args:
        trade_id (str): The identifier of the trade to close.
        
    Returns:
        dict or None: The JSON response if the trade was closed successfully; otherwise, None.
    """
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/trades/{trade_id}/close"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.put(url, headers=headers)
        if response.status_code == 200:
            logging.info(f"[CLOSE] Trade {trade_id} closed successfully.")
            return response.json()
        else:
            logging.error(f"[CLOSE] Failed to close trade {trade_id}. Status code: {response.status_code} Response: {response.text}")
            return None
    except Exception as e:
        logging.error(f"[CLOSE] Exception while closing trade {trade_id}: {e}")
        return None

def main():
    open_trades = get_open_trades()
    if open_trades is None:
        logging.error("[TEST] Error retrieving trades.")
        return
    if len(open_trades) == 0:
        logging.info("[TEST] No open trades found. Nothing to close.")
        return

    logging.info(f"[TEST] Found {len(open_trades)} open trades. Attempting to close all...")
    
    for trade in open_trades:
        trade_id = trade.get("id")
        if not trade_id:
            logging.error("[TEST] Trade data is missing an 'id'. Skipping trade.")
            continue
        logging.info(f"[TEST] Attempting to close trade {trade_id}...")
        result = close_trade(trade_id)
        if result:
            logging.info(f"[TEST] Trade {trade_id} closed. Response: {result}")
        else:
            logging.error(f"[TEST] Failed to close trade {trade_id}.")

if __name__ == "__main__":
    main()
