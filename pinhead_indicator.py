#!/usr/bin/env python3
import os
import time
import logging
import sqlite3

import pandas as pd
import requests
from finta import TA
from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

from config import BASE_URL, API_KEY, DATA_FOLDER, HISTORY_TABLE, FEEDBACK_MIN_TRADES
from trailing_stoploss_helper import close_trade_by_id
from risk_managment import RiskManager

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Strategy parameters
MIN_TRAILING_PIPS = 1
MAX_TRAILING_PIPS = 10
BUY_THRESHOLD = 0.003
SELL_THRESHOLD = -0.003
OPTIMAL_TRAILING_WINDOW = 14
LOSS_PENALTY = 2.0

# Paths
os.makedirs(DATA_FOLDER, exist_ok=True)
DB_FILE = os.path.join(DATA_FOLDER, "trade_info.db")

# Initialize RiskManager and control flag
rm = RiskManager()
first_run = True

def _ensure_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            instrument TEXT,
            time TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (instrument, time)
        )
    """)
    conn.commit()
    conn.close()

def update_db(records, instrument):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        for rec in records:
            c.execute(
                '''INSERT OR REPLACE INTO candles
                   (instrument, time, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (instrument,
                 rec['time'], rec['open'], rec['high'], rec['low'],
                 rec['close'], rec.get('volume', 0))
            )
        conn.commit()
    except Exception as e:
        logging.error(f"[update_db] Error: {e}")
    finally:
        conn.close()

def get_candles(instrument, granularity="M15", count=500):
    url = f"{BASE_URL}/instruments/{instrument}/candles"
    params = {"granularity": granularity, "count": count, "price": "M"}
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {API_KEY}"}, params=params)
        r.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Request error for {instrument} {granularity}: {e}")
        return pd.DataFrame(), []
    payload = r.json().get('candles', [])
    records = []
    for c in payload:
        if not c.get('complete'):
            continue
        m = c['mid']
        records.append({
            'time': c['time'], 'open': float(m['o']), 'high': float(m['h']),
            'low': float(m['l']), 'close': float(m['c']), 'volume': c.get('volume', 0)
        })
    df = pd.DataFrame(records)
    if not df.empty:
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
    return df, records

def add_indicators(df):
    df = df.copy()
    df['OBV'] = TA.OBV(df)
    df['RSI'] = TA.RSI(df, 14)
    ich = TA.ICHIMOKU(df)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)\
        .rolling(OPTIMAL_TRAILING_WINDOW).mean()
    return pd.concat([df, ich], axis=1)

def extract_features_and_labels(df):
    df = add_indicators(df).ffill().bfill()
    df['pred_return'] = df['close'].pct_change().shift(-1)
    df['opt_trail'] = (df['high'] - df['low']).rolling(OPTIMAL_TRAILING_WINDOW).mean()
    df = df.dropna()
    exclude = ['pred_return', 'opt_trail', 'open', 'high', 'low', 'close', 'volume']
    features = [c for c in df.columns if c not in exclude]
    X = df[features]
    y = df[['pred_return', 'opt_trail']]
    return X, y

def retrain_model(instrument):
    conn = sqlite3.connect(DB_FILE)
    try:
        hist = pd.read_sql_query(
            f"SELECT instrument, final_profit_pips, close_timestamp FROM {HISTORY_TABLE} WHERE instrument = ?",
            conn, params=(instrument,)
        )
        if len(hist) >= FEEDBACK_MIN_TRADES:
            X_list, y_list = [], []
            for _, row in hist.iterrows():
                ts = row['close_timestamp']
                cdf = pd.read_sql_query(
                    "SELECT time, open, high, low, close, volume FROM candles WHERE instrument = ? AND time <= ? ORDER BY time DESC LIMIT 1",
                    conn, params=(instrument, ts)
                )
                if cdf.empty(): continue
                cdf['time'] = pd.to_datetime(cdf['time'])
                cdf.set_index('time', inplace=True)
                feats = add_indicators(cdf).iloc[-1]
                X_list.append(feats.values)
                y_list.append(row['final_profit_pips'])
            if len(X_list) >= FEEDBACK_MIN_TRADES:
                X_hist = pd.DataFrame(X_list, columns=feats.index)
                y_hist = pd.Series(y_list)
                model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, random_state=42)
                model.fit(X_hist, y_hist)
                conn.close()
                return model, X_hist.columns.tolist()
    except Exception as e:
        logging.warning(f"[retrain_model] feedback loop failed: {e}")

    df = pd.read_sql_query(
        "SELECT time, open, high, low, close, volume FROM candles WHERE instrument = ? ORDER BY time",
        conn, params=(instrument,)
    )
    conn.close()
    if df.empty:
        return None, None
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    X, y = extract_features_and_labels(df)
    if len(X) < 100:
        logging.info(f"Not enough data for training {instrument}: {len(X)} rows")
        return None, None
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    model = MultiOutputRegressor(
        GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, random_state=42)
    )
    model.fit(X_train, y_train)
    return model, X.columns.tolist()

def generate_signal(inst, granularity):
    df_new, recs = get_candles(inst, granularity)
    if recs:
        _ensure_db()
        update_db(recs, inst)
    model, cols = retrain_model(inst)
    if model is None:
        return None
    df = add_indicators(df_new)
    latest = df.iloc[-1]
    feat = latest[cols].to_frame().T.ffill().fillna(0)
    pred = model.predict(feat)
    if isinstance(pred[0], (float, int)) or len(pred[0]) == 1:
        profit_pips = pred[0][0] if isinstance(pred[0], (list, tuple)) else pred[0]
        trailing = MIN_TRAILING_PIPS
    else:
        ret, raw_tr = pred[0]
        pip_size = 0.01 if 'JPY' in inst else 0.0001
        profit_pips = ret / pip_size
        tr_pips = raw_tr / pip_size
        trailing = max(MIN_TRAILING_PIPS, min(tr_pips, MAX_TRAILING_PIPS))
    sig = 'BUY' if profit_pips > BUY_THRESHOLD else 'SELL' if profit_pips < SELL_THRESHOLD else 'HOLD'

    # CUTE DISPLAY FOR HUMANS ❤️📈
    print("\n====================== POINT SYSTEM ======================")
    print(f"📊 Instrument      : {inst}")
    print(f"🕒 Timeframe       : {granularity}")
    print(f"📌 Prediction      : {sig}")
    print(f"✨ Predicted Pips  : {profit_pips:.2f}")
    print(f"🎯 Trailing Pips   : {trailing:.2f}")
    print("==========================================================\n")

    logging.info(
        f"Generated signal for {inst} {granularity}: "
        f"signal={sig}, predicted_pips={profit_pips:.2f}, trailing_pips={trailing:.2f}"
    )
    return {
        "instrument": inst,
        "timeframe": granularity,
        "signal": sig,
        "predicted_pips": profit_pips,
        "trailing_pips": trailing
    }

def generate_multiframe_signal(inst, timeframes=None):
    if timeframes is None:
        timeframes = ["M5", "M15", "H1"]
    signals = []
    for gran in timeframes:
        sig = generate_signal(inst, gran)
        if sig and sig.get("signal") != "HOLD":
            signals.append(sig)
    return signals
