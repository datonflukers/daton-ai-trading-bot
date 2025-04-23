import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Mode selection ---
# OANDA_MODE should be 'practice' or 'live'
OANDA_MODE = os.getenv("OANDA_MODE", "practice").lower()

# --- Base API URL ---
# Use the correct endpoint based on mode
if OANDA_MODE == 'live':
    BASE_URL = "https://api-fxtrade.oanda.com/v3"
else:
    BASE_URL = "https://api-fxpractice.oanda.com/v3"

# --- Account credentials ---
OANDA_ACCOUNT_ID_LIVE     = os.getenv("OANDA_ACCOUNT_ID_LIVE")
OANDA_API_KEY_LIVE        = os.getenv("OANDA_API_KEY_LIVE")
OANDA_ACCOUNT_ID_PRACTICE = os.getenv("OANDA_ACCOUNT_ID_PRACTICE")
OANDA_API_KEY_PRACTICE    = os.getenv("OANDA_API_KEY_PRACTICE")

# Derived credentials for current mode
ACCOUNT_ID = (
    OANDA_ACCOUNT_ID_LIVE     if OANDA_MODE == 'live' else OANDA_ACCOUNT_ID_PRACTICE
)
API_KEY    = (
    OANDA_API_KEY_LIVE        if OANDA_MODE == 'live' else OANDA_API_KEY_PRACTICE
)

# --- Data & execution settings ---
DATA_FOLDER           = os.getenv("DATA_FOLDER", ".")
ORDER_SIZE            = int(os.getenv("ORDER_SIZE", 1000))
CYCLE_INTERVAL        = int(os.getenv("CYCLE_INTERVAL", 300))
RISK_UPDATE_INTERVAL  = int(os.getenv("RISK_UPDATE_INTERVAL", 60))

# --- Stop -loss & take -profit parameters ---
ACTIVATION_THRESHOLD  = int(os.getenv("ACTIVATION_THRESHOLD", 20))    # pips to start trailing
TRAILING_GAP          = int(os.getenv("TRAILING_GAP", 10))            # pips retracement to close
POLL_INTERVAL         = int(os.getenv("POLL_INTERVAL", 60))           # stop -loss monitor frequency (s)
TAKE_PROFIT_PIPS      = int(os.getenv("TAKE_PROFIT_PIPS", 70))         # fixed TP target in pips

# --- ATR -based stop -loss bounds ---
# When initializing or adjusting stops via ATR, clamp between these pips
ATR_STOP_MIN_PIPS     = int(os.getenv("ATR_STOP_MIN_PIPS", 50))
ATR_STOP_MAX_PIPS     = int(os.getenv("ATR_STOP_MAX_PIPS", 100))

# --- Feedback training config ---
FEEDBACK_MIN_TRADES   = int(os.getenv("FEEDBACK_MIN_TRADES", 10))
HISTORY_TABLE          = os.getenv("HISTORY_TABLE", "trade_history")