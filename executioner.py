#!/usr/bin/env python3
"""
executioner.py

This module handles order execution for market orders.
It uses the credentials and mode provided in config.py.
Always runs in the mode configured by OANDA_MODE (live/practice).
"""

import logging
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
from colorama import init, Fore, Style
from config import ACCOUNT_ID, API_KEY, BASE_URL, OANDA_MODE

# Initialize colorama for colored terminal output
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Initialize the OANDA API client
api = API(access_token=API_KEY, environment=OANDA_MODE)


def execute_market_order(instrument, units):
    """
    Executes a market order for the given instrument and units.

    Args:
        instrument (str): The trading instrument (e.g., "EUR_USD").
        units (int): The number of units to buy (positive) or sell (negative).

    Returns:
        dict: The response from the OANDA API.
    """
    order_data = {
        "order": {
            "instrument": instrument,
            "units": str(units),
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }

    logging.info(f"{Fore.GREEN}Placing market order: {order_data}")
    try:
        r = orders.OrderCreate(accountID=ACCOUNT_ID, data=order_data)
        response = api.request(r)
        logging.info(f"{Fore.CYAN}Order executed successfully: {response}")
        return response
    except Exception as e:
        logging.error(f"{Fore.RED}Failed to execute order: {e}")
        raise


if __name__ == "__main__":
    # Example usage
    try:
        instrument = "EUR_USD"
        units = 1000  # Positive for buy, negative for sell
        response = execute_market_order(instrument, units)
        print(f"{Style.BRIGHT}{Fore.GREEN}Order Response: {response}")
    except Exception as e:
        print(f"{Style.BRIGHT}{Fore.RED}Error: {e}")
