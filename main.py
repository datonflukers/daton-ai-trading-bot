#!/usr/bin/env python3
import time
import threading
import logging
import schedule
import itertools
import sys
import requests

from datetime import datetime
from config import OANDA_MODE
from pinhead_indicator import generate_multiframe_signal
from risk_managment import RiskManager
from trailing_stoploss_helper import live_trailing_stop_monitor
from trade_profit_monitor import main as profit_monitor_main, get_current_price

# Instruments to evaluate
INSTRUMENTS = [
    "EUR_USD", "USD_JPY", "GBP_USD", "USD_CHF",
    "AUD_USD", "NZD_USD", "USD_CAD",
    "EUR_GBP", "EUR_JPY", "GBP_JPY"
]

# Entry thresholds and intervals
ENTRY_THRESHOLD_PIPS = 50.0
CONDITIONAL_INTERVAL = 120  # seconds
last_entry_time = 0

# Connection state flag
enabled = True

# Initialize RiskManager
rm = RiskManager()

# Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

# Heartbeat / Health-check logic
spinner = itertools.cycle(["🐰", "🌟", "🐱", "✨"])

def check_connection():
    global enabled
    try:
        # simple GET to check internet connectivity
        requests.get("https://api-fxtrade.oanda.com/v3/accounts", timeout=5)
        if not enabled:
            logging.info("✅ Connection restored; resuming operations.")
        enabled = True
    except Exception:
        if enabled:
            enabled = False
            logging.warning("🔌 Connection lost; pausing operations until reconnected.")
        raise


def reconnect():
    # cute spinner animation before reconnect logic
    for _ in range(10):
        emo = next(spinner)
        sys.stdout.write(f"\r{emo}  Reconnecting... {emo}")
        sys.stdout.flush()
        time.sleep(0.2)
    sys.stdout.write("\r🔌 Connection lost — re-establishing! 🔌\n")

    # Wait until real OANDA API responds
    while True:
        try:
            requests.get("https://api-fxtrade.oanda.com/v3/accounts", timeout=5)
            print("✅ Reconnected!\n")
            break
        except Exception:
            emo = next(spinner)
            sys.stdout.write(f"\r{emo}  Still reconnecting… {emo}")
            sys.stdout.flush()
            time.sleep(2)

class ConnectionMonitor(threading.Thread):
    def __init__(self, check_fn, interval=15):
        super().__init__(daemon=True)
        self.check_fn = check_fn
        self.interval = interval

    def run(self):
        global enabled
        while True:
            try:
                self.check_fn()
            except Exception:
                reconnect()
            time.sleep(self.interval)


def job_multiframe():
    if not enabled:
        logging.info("⏸️ Skipping entry job; no connection.")
        return
    logging.info("🕒 Running multiframe entry job...")
    if not rm.get_live_positions():
        all_signals = []
        for inst in INSTRUMENTS:
            all_signals.extend(
                generate_multiframe_signal(inst, ["M5", "M15", "H1"]))
        viable = [s for s in all_signals if abs(s['predicted_pips']) >= ENTRY_THRESHOLD_PIPS]
        if viable:
            best = max(viable, key=lambda x: abs(x['predicted_pips']))
            side = 'long' if best['signal']=='BUY' else 'short'
            logging.info(
                f"✅ Executing {best['timeframe']} {best['signal']} on {best['instrument']} "
                f"for {best['predicted_pips']:.2f} pips"
            )
            rm.confirm_trade(best['instrument'], side)
        else:
            logging.info(f"No signals ≥ {ENTRY_THRESHOLD_PIPS} pips; skipping entry.")
    else:
        logging.info(f"⚠️ Position open: {list(rm.get_live_positions().keys())}; no entry.")


def job_risk_management():
    if not enabled:
        logging.info("⏸️ Skipping risk-management job; no connection.")
        return
    global last_entry_time
    prices = {inst: get_current_price(inst) for inst in INSTRUMENTS}
    rm.update_all_positions(prices)

    if not rm.get_live_positions():
        now = time.time()
        if now - last_entry_time >= CONDITIONAL_INTERVAL:
            logging.info("🔄  Conditional entry triggered by risk_management job")
            job_multiframe()
            last_entry_time = now


def main():  # Based on original main.py citeturn0file0
    logging.info(f"Scheduler starting in {OANDA_MODE.upper()} mode")

    # Start profit monitor thread
    threading.Thread(target=profit_monitor_main, daemon=True).start()

    # Start trailing-stop monitor
    threading.Thread(target=live_trailing_stop_monitor, daemon=True).start()

    # Start the heartbeat thread
    monitor = ConnectionMonitor(check_connection, interval=15)
    monitor.start()

    # Schedule entry and risk-management jobs
    schedule.every(5).minutes.do(job_multiframe)
    schedule.every(1).minutes.do(job_risk_management)

    # Initial runs
    job_multiframe()
    job_risk_management()

    # Enter the scheduler loop
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
