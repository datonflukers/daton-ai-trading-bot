#!/usr/bin/env python3
"""
trade_profit_monitor.py

Continuously fetches open trades from OANDA, updates the local SQLite database
with profit snapshots, and records final outcomes of closed trades into a history table.
"""
import os
import time
import datetime
import sqlite3
import requests
import logging

from config import (
    OANDA_MODE,
    OANDA_API_KEY_LIVE,
    OANDA_API_KEY_PRACTICE,
    OANDA_ACCOUNT_ID_LIVE,
    OANDA_ACCOUNT_ID_PRACTICE,
    DATA_FOLDER
)
from shared_data import update_predicted_profit

# Constants
ACCOUNT_ID = (
    OANDA_ACCOUNT_ID_LIVE if OANDA_MODE == 'live'
    else OANDA_ACCOUNT_ID_PRACTICE
)
API_KEY = (
    OANDA_API_KEY_LIVE if OANDA_MODE == 'live'
    else OANDA_API_KEY_PRACTICE
)
BASE_URL = "https://api-fxtrade.oanda.com/v3"
DB_FILE = os.path.join(DATA_FOLDER, "trade_info.db")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s"
)

# Table creation queries
CREATE_PROFITS_QUERY = """
CREATE TABLE IF NOT EXISTS trade_profits (
    trade_id TEXT,
    instrument TEXT,
    profit_pips REAL,
    profit_usd REAL,
    timestamp TEXT,
    PRIMARY KEY (trade_id, timestamp)
)
"""

CREATE_HISTORY_QUERY = """
CREATE TABLE IF NOT EXISTS trade_history (
    trade_id TEXT PRIMARY KEY,
    instrument TEXT,
    final_profit_pips REAL,
    final_profit_usd REAL,
    close_timestamp TEXT
)
"""

# Track currently open trade IDs to detect closures
detected_open = set()


def initialize_database():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(CREATE_PROFITS_QUERY)
    c.execute(CREATE_HISTORY_QUERY)
    conn.commit()
    conn.close()


def get_current_price(instrument):
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/pricing?instruments={instrument}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
        if prices:
            bid = float(prices[0]["bids"][0]["price"])
            ask = float(prices[0]["asks"][0]["price"])
            return (bid + ask) / 2
    except Exception as e:
        logging.error(f"[get_current_price] Error for {instrument}: {e}")
    return None


def fetch_trade_data():
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/trades"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    open_trades = []
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        trades = resp.json().get("trades", [])
        for tr in trades:
            tid = tr.get("id")
            inst = tr.get("instrument")
            entry = float(tr.get("price"))
            current = get_current_price(inst)
            if current is None:
                continue
            pip_size = 0.01 if 'JPY' in inst.upper() else 0.0001
            units = tr.get("initialUnits", "")
            profit_pips = (
                (current - entry) / pip_size
                if str(units).startswith('-') is False
                else (entry - current) / pip_size
            )
            profit_usd = float(tr.get("unrealizedPL", 0))
            # Update shared_data for trailing
            update_predicted_profit(inst, profit_pips)
            open_trades.append({
                "trade_id": tid,
                "instrument": inst,
                "calculated_profit_pips": profit_pips,
                "unrealized_pl_usd": profit_usd
            })
    except Exception as e:
        logging.error(f"[fetch_trade_data] {e}")

    # Detect closed trades
    global detected_open
    current_ids = {t['trade_id'] for t in open_trades}
    closed_ids = detected_open - current_ids
    if closed_ids:
        record_trade_history(closed_ids)
    detected_open = current_ids

    # Persist profit snapshots
    update_trade_profits_database(open_trades)
    return open_trades


def update_trade_profits_database(trades):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for t in trades:
        c.execute(
            '''INSERT OR REPLACE INTO trade_profits
               (trade_id, instrument, profit_pips, profit_usd, timestamp)
               VALUES (?, ?, ?, ?, ?)''',
            (
                t["trade_id"],
                t["instrument"],
                t["calculated_profit_pips"],
                t["unrealized_pl_usd"],
                datetime.datetime.now().isoformat()
            )
        )
    conn.commit()
    conn.close()


def record_trade_history(closed_ids):
    """
    For each closed trade_id, take its last profit snapshot and store final outcome.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for tid in closed_ids:
        # Get last entry from trade_profits
        c.execute(
            '''SELECT instrument, profit_pips, profit_usd, timestamp
               FROM trade_profits
               WHERE trade_id = ?
               ORDER BY timestamp DESC LIMIT 1''',
            (tid,)
        )
        row = c.fetchone()
        if row:
            inst, pips, usd, ts = row
            close_ts = datetime.datetime.now().isoformat()
            c.execute(
                '''INSERT OR REPLACE INTO trade_history
                   (trade_id, instrument, final_profit_pips, final_profit_usd, close_timestamp)
                   VALUES (?, ?, ?, ?, ?)''',
                (tid, inst, pips, usd, close_ts)
            )
            logging.info(f"[History] Recorded closed trade {tid}: pips={pips:.2f}, usd={usd:.2f}")
    conn.commit()
    conn.close()


def main():
    initialize_database()
    while True:
        logging.info(f"=== Trade Info at {datetime.datetime.now()} ===")
        trades = fetch_trade_data()
        if trades:
            for t in trades:
                print(f"Trade ID: {t['trade_id']} | Instrument: {t['instrument']}")
                print(f"  Pips: {t['calculated_profit_pips']:.2f} | USD P/L: {t['unrealized_pl_usd']:.2f}")
        else:
            print("No open trades.")
        time.sleep(60)


if __name__ == '__main__':
    main()