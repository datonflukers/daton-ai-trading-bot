# inspect_db.py
import sqlite3
import pandas as pd
import os

# ─── UPDATE THIS PATH ───
DB_PATH = r"C:\Users\daton\OneDrive\Desktop\OandaBaby\OandaTradingBot\data.db"

if not os.path.isfile(DB_PATH):
    raise FileNotFoundError(f"No database found at {DB_PATH}")

conn = sqlite3.connect(DB_PATH)

# 1) Count of candles per instrument
df_counts = pd.read_sql_query(
    """
    SELECT
      instrument,
      COUNT(*) AS total_candles,
      MIN(time) AS first_timestamp,
      MAX(time) AS last_timestamp
    FROM candles
    GROUP BY instrument
    """,
    conn
)

print("\n── Candle Counts & Date Range ─────────────────────")
print(df_counts.to_string(index=False))
print("──────────────────────────────────────────────────\n")

# 2) Five most recent candles for each instrument
for inst in df_counts["instrument"].tolist():
    df_recent = pd.read_sql_query(
        f"""
        SELECT time, open, high, low, close
        FROM candles
        WHERE instrument = '{inst}'
        ORDER BY time DESC
        LIMIT 5
        """,
        conn
    )
    print(f"── 5 Most Recent Candles for {inst} ─────────────")
    print(df_recent.to_string(index=False))
    print("──────────────────────────────────────────────────\n")

conn.close()
