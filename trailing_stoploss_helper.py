#!/usr/bin/env python3
"""
trailing_stoploss_helper.py

Standalone module for live trailing-stop execution on OANDA trades.
Implements:
  - Fixed take-profit
  - Peak profit tracking
  - Activation threshold and retracement-based stop-loss
"""
import logging
import time
from oandapyV20 import API
import oandapyV20.endpoints.trades as trades_ep
from risk_managment import fetch_open_trades, fetch_current_price
from shared_data import shared_risk_data, clear_predicted_profit
from config import (
    OANDA_MODE,
    OANDA_API_KEY_LIVE,
    OANDA_API_KEY_PRACTICE,
    OANDA_ACCOUNT_ID_LIVE,
    OANDA_ACCOUNT_ID_PRACTICE,
    ACTIVATION_THRESHOLD,
    TRAILING_GAP,
    POLL_INTERVAL,
    TAKE_PROFIT_PIPS
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Determine credentials
API_KEY = (
    OANDA_API_KEY_LIVE if OANDA_MODE == 'live' else OANDA_API_KEY_PRACTICE
)
ACCOUNT_ID = (
    OANDA_ACCOUNT_ID_LIVE if OANDA_MODE == 'live' else OANDA_ACCOUNT_ID_PRACTICE
)

# Build client
client = API(access_token=API_KEY, environment=OANDA_MODE)

# Cooldown for recently closed instruments
COOLDOWN_PERIOD = POLL_INTERVAL * 5

# Trackers
peaks = {}             # trade_id -> highest profit seen
recently_closed = {}   # instrument -> timestamp when closed
recently_closed_trades = recently_closed  # alias for external access   # instrument -> timestamp when closed


def close_trade_by_id(trade_id, instrument):
    """
    Close a trade via OANDA API and clear its shared state.
    """
    endpoint = trades_ep.TradeClose(accountID=ACCOUNT_ID, tradeID=trade_id)
    client.request(endpoint)
    logger.info(f"[Trailing] Closed trade {trade_id} on {instrument}")
    recently_closed[instrument] = time.time()
    peaks.pop(trade_id, None)
    clear_predicted_profit(instrument)


def live_trailing_stop_monitor():
    """
    Continuous loop:
      1. Enforce fixed TP if profit >= TAKE_PROFIT_PIPS
      2. Track peak profit
      3. Activate trailing-stop after ACTIVATION_THRESHOLD reached
      4. Close trade if retracement from peak >= TRAILING_GAP
    """
    logger.info("[Trailing] Starting live trailing-stop monitor...")
    while True:
        trades = fetch_open_trades()
        insts = [t['instrument'] for t in trades]
        logger.debug(f"[Trailing] Live positions: {insts}")

        for t in trades:
            tid = t.get('id')
            inst = t.get('instrument')

            # Cooldown check
            if inst in recently_closed and (time.time() - recently_closed[inst]) < COOLDOWN_PERIOD:
                logger.debug(f"[Trailing] {inst} in cooldown period")
                continue

            # Determine current profit in pips (prefer shared state)
            shared = shared_risk_data.get(inst, {}).get('predicted_profit_pips')
            if shared is not None:
                profit = shared
                logger.info(f"[Trailing] {inst} profit from shared: {profit:.2f} pips")
            else:
                entry = float(t.get('price', 0))
                current = fetch_current_price(inst)
                if current is None:
                    logger.error(f"[Trailing] Could not fetch price for {inst}")
                    continue
                pip_size = 0.01 if 'JPY' in inst.upper() else 0.0001
                units = float(t.get('currentUnits', t.get('initialUnits', 0)))
                profit = ((current - entry) / pip_size) if units > 0 else ((entry - current) / pip_size)
                logger.info(f"[Trailing] {inst} computed profit: {profit:.2f} pips")

            # 1. Fixed Take-Profit
            if profit >= TAKE_PROFIT_PIPS:
                logger.info(f"[Trailing] {inst} reached TP ({profit:.2f} >= {TAKE_PROFIT_PIPS}), closing.")
                close_trade_by_id(tid, inst)
                continue

            # 2. Peak tracking
            old_peak = peaks.get(tid, profit)
            new_peak = max(old_peak, profit)
            peaks[tid] = new_peak
            if new_peak != old_peak:
                logger.info(f"[Trailing] {inst} new peak: {new_peak:.2f} pips (was {old_peak:.2f})")

            # 3. Activation
            if old_peak < ACTIVATION_THRESHOLD <= new_peak:
                logger.info(f"[Trailing] {inst} activated trailing-stop at {new_peak:.2f} pips")

            # 4. Trailing logic
            if new_peak >= ACTIVATION_THRESHOLD:
                retrace = new_peak - profit
                if retrace >= TRAILING_GAP:
                    logger.info(f"[Trailing] {inst} retracement {retrace:.2f} >= gap {TRAILING_GAP}, closing.")
                    close_trade_by_id(tid, inst)
                else:
                    logger.debug(f"[Trailing] {inst} trailing (retrace {retrace:.2f} < gap {TRAILING_GAP})")
            else:
                logger.debug(f"[Trailing] {inst} peak {new_peak:.2f} below activation {ACTIVATION_THRESHOLD}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    live_trailing_stop_monitor()
