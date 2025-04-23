"""
shared_data.py

This module holds shared risk management data in a single dictionary.
It is used by risk_managment.py, trailing_stoploss_helper.py, and the profit monitor
for coordinating profit values and cleanup when trades close.
"""

shared_risk_data = {}


def reset_shared_risk_data():
    """
    Reset the entire shared risk data dictionary (use only when no trade is active).
    """
    global shared_risk_data
    shared_risk_data.clear()
    print("[Shared Data] Shared risk data has been reset.")


def update_predicted_profit(instrument, predicted_profit_pips):
    """
    Update the predicted profit in pips for a specific instrument.
    """
    global shared_risk_data
    if instrument not in shared_risk_data:
        shared_risk_data[instrument] = {}
    shared_risk_data[instrument]["predicted_profit_pips"] = predicted_profit_pips
    shared_risk_data[instrument]["last_update"] = datetime.datetime.utcnow().isoformat()
    print(f"[Shared Data] Updated predicted profit for {instrument}: {predicted_profit_pips} pips.")


def get_predicted_profit(instrument):
    """
    Retrieve the latest predicted profit pips for an instrument, or None if unavailable.
    """
    return shared_risk_data.get(instrument, {}).get("predicted_profit_pips")


def clear_predicted_profit(instrument):
    """
    Remove stored profit data for an instrument (e.g., when a trade closes).
    """
    global shared_risk_data
    if instrument in shared_risk_data:
        shared_risk_data.pop(instrument)
        print(f"[Shared Data] Cleared predicted profit for {instrument}.")

import datetime
import pandas as pd


def convert_and_fill_shared_data():
    """
    Convert object columns in shared_risk_data to nullable extension types and fill missing values.
    """
    global shared_risk_data
    for instrument, data in list(shared_risk_data.items()):
        if isinstance(data, pd.DataFrame):
            shared_risk_data[instrument] = data.convert_dtypes().fillna(False)
            print(f"[Shared Data] Converted and filled data for {instrument}.")
