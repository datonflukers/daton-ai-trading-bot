#!/usr/bin/env python3
import logging
import time
import datetime
import config
from oandapyV20 import API
import oandapyV20.endpoints.trades as trades_ep
from risk_managment import fetch_open_trades, fetch_current_price
from config import ACTIVATION_THRESHOLD, TRAILING_GAP, POLL_INTERVAL, TAKE_PROFIT_PIPS
from shared_data import shared_risk_data, clear_predicted_profit

# Initialize logger
logger = logging.getLogger(__name__)

# Build OANDA API client with live credentials
client = API(access_token=config.API_KEY, environment=config.OANDA_MODE)

# Cooldown for recently closed instruments (to prevent immediate re-entry)
COOLDOWN_PERIOD = POLL_INTERVAL * 5

# Internal trackers for peak profits and recently closed instruments
peaks = {}
recently_closed_trades = {}


def close_trade_by_id(trade_id, instrument):
    """
    Close the specified trade by issuing a market close request and start cooldown.
    Also clear shared profit state.
    """
    endpoint = trades_ep.TradeClose(accountID=config.ACCOUNT_ID, tradeID=trade_id)
    client.request(endpoint)
    logger.info(f"Closed trade {trade_id} on {instrument}")
    recently_closed_trades[instrument] = time.time()
    peaks.pop(trade_id, None)
    clear_predicted_profit(instrument)


def live_trailing_stop_monitor():
    """
    Core trailing-stop logic:
      1. Enforce fixed take-profit at TAKE_PROFIT_PIPS
      2. Track peak profit
      3. Close if profit retraces by TRAILING_GAP from peak (once activated)
    Runs continuously, polling every POLL_INTERVAL seconds.
    """
    logger.info("Starting live trailing-stop monitor...")
    while True:
        open_trades = fetch_open_trades()
        for t in open_trades:
            tid = t.get('id')
            inst = t.get('instrument')

            # Skip instruments in cooldown
            if inst in recently_closed_trades and (time.time() - recently_closed_trades[inst]) < COOLDOWN_PERIOD:
                continue

            # Use shared profit if available, else compute locally
            shared = shared_risk_data.get(inst, {}).get('predicted_profit_pips')
            if shared is not None:
                profit_pips = shared
            else:
                entry_price = float(t.get('price', 0))
                current_price = fetch_current_price(inst)
                if current_price is None:
                    continue
                pip_size = 0.01 if 'JPY' in inst.upper() else 0.0001
                units = float(t.get('currentUnits', t.get('initialUnits', 0)))
                profit_pips = ((current_price - entry_price) / pip_size) if units > 0 else ((entry_price - current_price) / pip_size)

            # 1. Fixed take-profit
            if profit_pips >= TAKE_PROFIT_PIPS:
                logger.info(f"Take-profit reached {profit_pips:.1f} pips on {inst}. Closing trade.")
                close_trade_by_id(tid, inst)
                continue

            # 2. Track peak profit
            peaks[tid] = max(peaks.get(tid, profit_pips), profit_pips)

            # 3. Retracement check
            if peaks[tid] >= ACTIVATION_THRESHOLD and (peaks[tid] - profit_pips) >= TRAILING_GAP:
                logger.info(f"Trade {tid} on {inst} retraced {peaks[tid] - profit_pips:.1f} pips from peak {peaks[tid]:.1f}. Closing trade.")
                close_trade_by_id(tid, inst)

        time.sleep(POLL_INTERVAL)
