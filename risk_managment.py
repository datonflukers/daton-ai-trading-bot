#!/usr/bin/env python3
# risk_managment.py
# Hard‑coded SL=50 pips, TP=70 pips; self‑scheduling for update & entry
import logging
import requests
import pandas as pd
import schedule
import time

import config

# Instruments list for entry logic
INSTRUMENTS = [
    "EUR_USD", "USD_JPY", "GBP_USD", "USD_CHF",
    "AUD_USD", "NZD_USD", "USD_CAD",
    "EUR_GBP", "EUR_JPY", "GBP_JPY"
]

# OANDA credentials from config
ACCOUNT_ID = (
    config.OANDA_ACCOUNT_ID_LIVE if config.OANDA_MODE == 'live'
    else config.OANDA_ACCOUNT_ID_PRACTICE
)
API_KEY = (
    config.OANDA_API_KEY_LIVE if config.OANDA_MODE == 'live'
    else config.OANDA_API_KEY_PRACTICE
)
BASE_URL = config.BASE_URL
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Entry threshold and intervals
ENTRY_THRESHOLD_PIPS = 50.0
CONDITIONAL_INTERVAL = 120  # seconds

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")


def fetch_open_trades() -> list:
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/openTrades"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.json().get('trades', [])
    except Exception as e:
        logging.error(f"[fetch_open_trades] API error: {e}")
        return []


def fetch_current_price(instrument: str) -> float:
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/pricing"
    resp = requests.get(url, headers=HEADERS, params={'instruments': instrument})
    resp.raise_for_status()
    prices = resp.json().get('prices', [])
    if not prices:
        return None
    p = prices[0]
    return (float(p['bids'][0]['price']) + float(p['asks'][0]['price'])) / 2


class RiskManager:
    def __init__(self):
        self.active_trade = None
        logging.info("RiskManager initialized.")

    def get_live_positions(self) -> dict:
        trades = fetch_open_trades()
        positions = {}
        for t in trades:
            inst = t.get('instrument')
            entry = float(t.get('price', 0))
            units = int(t.get('initialUnits', 0))
            side = 'long' if units > 0 else 'short'
            positions[inst] = {'trade_id': t.get('id'), 'instrument': inst, 'entry_price': entry, 'side': side}
        if positions:
            logging.info(f"Live positions: {list(positions.keys())}")
            self.active_trade = next(iter(positions.values()))
        else:
            logging.info("No live positions.")
            self.active_trade = None
        return positions

    def confirm_trade(self, instrument: str, side: str) -> str:
        """Place market order with SL=50p and TP=70p."""
        price = fetch_current_price(instrument)
        if price is None:
            logging.error(f"Cannot fetch price for {instrument}, aborting.")
            return None
        pip_size = 0.01 if 'JPY' in instrument.upper() else 0.0001
        units = config.ORDER_SIZE if side == 'long' else -config.ORDER_SIZE

        sl_pips = 50.0
        tp_pips = 70.0
        if side == 'long':
            sl_price = price - sl_pips * pip_size
            tp_price = price + tp_pips * pip_size
        else:
            sl_price = price + sl_pips * pip_size
            tp_price = price - tp_pips * pip_size

        logging.info(
            f"[Order] {side} {instrument}: SL {sl_pips}p @ {sl_price:.5f}, TP {tp_pips}p @ {tp_price:.5f}"
        )
        body = {"order": {
            "instrument": instrument,
            "units": str(units),
            "type": "MARKET",
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{sl_price:.5f}"},
            "takeProfitOnFill": {"price": f"{tp_price:.5f}"}
        }}
        url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders"
        resp = requests.post(url, headers=HEADERS, json=body)
        resp.raise_for_status()
        tid = resp.json().get('orderFillTransaction', {}).get('orderID')
        logging.info(f"Trade placed: {side} {instrument}, ID {tid}")
        self.active_trade = {'trade_id': tid, 'instrument': instrument, 'entry_price': price, 'side': side}
        return tid

    def close_trade_by_id(self, trade_id: str):
        url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/trades/{trade_id}/close"
        resp = requests.put(url, headers=HEADERS)
        if resp.status_code == 200:
            logging.info(f"Closed trade {trade_id}")
        else:
            logging.error(f"Error closing trade {trade_id}: {resp.text}")

    def update_all_positions(self, prices: dict):
        """Update P/L and auto-close TP/SL."""
        if not self.active_trade:
            return
        inst = self.active_trade['instrument']
        tid = self.active_trade['trade_id']
        cp = prices.get(inst)
        if cp is None:
            return
        ep = self.active_trade['entry_price']
        pip_size = 0.01 if 'JPY' in inst.upper() else 0.0001
        profit = (cp - ep)/pip_size if self.active_trade['side']=='long' else (ep - cp)/pip_size
        logging.info(f"Trade {tid} profit: {profit:.2f} pips")
        # Auto-close
        if profit >= 70.0 or profit <= -50.0:
            self.close_trade_by_id(tid)
            self.active_trade = None

    def calculate_profit(self, trade: dict, price: float) -> float:
        pip_size = 0.01 if 'JPY' in trade['instrument'].upper() else 0.0001
        return ((price - trade['entry_price'])/pip_size
                if trade['side']=='long'
                else (trade['entry_price'] - price)/pip_size)

# --- Scheduler for risk & conditional entry ---

def conditional_entry(rm: RiskManager):
    # defer import to avoid circular dependency
    from pinhead_indicator import generate_multiframe_signal

    if not rm.get_live_positions():
        logging.info("🔄 Running conditional entry (no open trades)")
        all_sigs = []
        for inst in INSTRUMENTS:
            all_sigs.extend(generate_multiframe_signal(inst, ["M5","M15","H1"]))
        viable = [s for s in all_sigs if abs(s['predicted_pips'])>=ENTRY_THRESHOLD_PIPS]
        if viable:
            best = max(viable, key=lambda x: abs(x['predicted_pips']))
            side = 'long' if best['signal']=='BUY' else 'short'
            rm.confirm_trade(best['instrument'], side)


if __name__ == '__main__':
    rm = RiskManager()
    # Schedule updates
    schedule.every(1).minutes.do(lambda: rm.update_all_positions(
        {inst: fetch_current_price(inst) for inst in INSTRUMENTS}
    ))
    schedule.every(2).minutes.do(lambda: conditional_entry(rm))

    # Initial run
    conditional_entry(rm)
    rm.update_all_positions({inst: fetch_current_price(inst) for inst in INSTRUMENTS})

    # Loop forever
    while True:
        schedule.run_pending()
        time.sleep(1)
