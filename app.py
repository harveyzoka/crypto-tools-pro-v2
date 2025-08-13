import streamlit as st
import pandas as pd
import numpy as np
import ccxt, requests, plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="Crypto Tools Pro V2", layout="wide")
st.title("🚀 Crypto Tools Pro V2")

# Strategy functions
def ema(series, span): return series.ewm(span=span, adjust=False).mean()
def rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta>0, delta, 0.0)
    loss = np.where(delta<0, -delta, 0.0)
    roll_up = pd.Series(gain).rolling(period).mean()
    roll_down = pd.Series(loss).rolling(period).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    return 100 - (100 / (1 + rs))
def bollinger(series, period=20, std_mult=2):
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return ma, ma + std_mult*std, ma - std_mult*std

def compute_strategy(df, strategy, **params):
    d = df.copy()
    if strategy == "EMA Crossover":
        fast, slow = params["fast"], params["slow"]
        d["ema_fast"] = ema(d["close"], fast)
        d["ema_slow"] = ema(d["close"], slow)
        d["signal"] = np.where(d["ema_fast"] > d["ema_slow"], 1, -1)
    elif strategy == "RSI2":
        d["rsi2"] = rsi(d["close"], 2)
        d["signal"] = np.where(d["rsi2"] < 10, 1, np.where(d["rsi2"] > 90, -1, 0))
    elif strategy == "Bollinger":
        ma, upper, lower = bollinger(d["close"], params.get("period",20), params.get("std_mult",2))
        d["signal"] = np.where(d["close"] < lower, 1, np.where(d["close"] > upper, -1, 0))
    elif strategy == "Breakout":
        lookback = params.get("lookback",20)
        d["high_max"] = d["high"].rolling(lookback).max()
        d["low_min"] = d["low"].rolling(lookback).min()
        d["signal"] = np.where(d["close"] > d["high_max"].shift(1), 1,
                               np.where(d["close"] < d["low_min"].shift(1), -1, 0))
    return d

def backtest(df, fee_bps=5):
    d = df.copy()
    d["ret"] = d["close"].pct_change().fillna(0)
    d["pos"] = d["signal"].shift(1).fillna(0)
    trade_change = d["pos"].diff().abs().fillna(0)
    fee = trade_change * (fee_bps/10000.0)
    d["strategy_ret"] = d["pos"] * d["ret"] - fee
    d["equity"] = (1 + d["strategy_ret"]).cumprod()
    return d

def export_to_gsheets(df, sheet_id, worksheet_name, json_keyfile):
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id).worksheet(worksheet_name)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    return True

# Sidebar controls
exchange = st.sidebar.selectbox("Exchange", ["binance", "bybit"])
symbol = st.sidebar.text_input("Symbol", "BTC/USDT")
timeframe = st.sidebar.selectbox(
    "Timeframe",
    ["1m","3m","5m","15m","30m","1h","4h","1d"],
    index=5
)

strategy = st.sidebar.selectbox("Strategy", ["EMA Crossover", "RSI2", "Bollinger", "Breakout"])
limit = st.sidebar.slider("Candles", 200, 2000, 500, 100)

# Load data
ex = getattr(ccxt, exchange)()
data = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
df["datetime"] = pd.to_datetime(df["ts"], unit="ms")

# Params
params = {}
if strategy=="EMA Crossover":
    params["fast"] = st.sidebar.number_input("EMA Fast", 2, 50, 9)
    params["slow"] = st.sidebar.number_input("EMA Slow", 2, 100, 21)
elif strategy=="Bollinger":
    params["period"] = st.sidebar.number_input("Period", 5, 50, 20)
    params["std_mult"] = st.sidebar.number_input("Std Mult", 1, 5, 2)
elif strategy=="Breakout":
    params["lookback"] = st.sidebar.number_input("Lookback", 2, 100, 20)

df = compute_strategy(df, strategy, **params)
bt = backtest(df)

# Plotly candlestick + equity overlay
fig = go.Figure(data=[
    go.Candlestick(x=df["datetime"], open=df["open"], high=df["high"],
                   low=df["low"], close=df["close"], name="Price"),
    go.Scatter(x=df["datetime"], y=bt["equity"]*df["close"].iloc[0],
               mode="lines", name="Equity (scaled)")
])
st.plotly_chart(fig, use_container_width=True)

# Export to Google Sheets
with st.expander("📤 Export Trade Log to Google Sheets"):
    sheet_id = st.text_input("Google Sheet ID")
    worksheet_name = st.text_input("Worksheet name", "Sheet1")
    json_keyfile = st.text_input("Service Account JSON path", "gcp_service_account.json")
    if st.button("Export now"):
        try:
            export_to_gsheets(bt, sheet_id, worksheet_name, json_keyfile)
            st.success("Exported successfully.")
        except Exception as e:
            st.error(str(e))
