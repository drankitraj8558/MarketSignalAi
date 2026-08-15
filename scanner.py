import os
import json
from datetime import datetime
import pytz
import requests
import yfinance as yf
import pandas as pd
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def send_telegram_alert(message_text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message_text, "parse_mode": "HTML"}
    requests.post(url, json=payload)

def generate_ai_analysis(ticker, price, rsi, ema200, signal_type, macd_status):
    if not client:
        return f"{signal_type} momentum trigger with RSI {rsi}."
    prompt = (
        f"Analyze this {signal_type} setup for Indian stock {ticker}:\n"
        f"- Price: ₹{price}\n"
        f"- RSI (14): {rsi}\n"
        f"- 200 EMA: ₹{ema200}\n"
        f"- MACD Status: {macd_status}\n\n"
        f"Give a concise 2-sentence trading thesis: 1. Core reason for the {signal_type}. 2. Specific Stop Loss and Target level."
    )
    
    # Updated to prioritize Gemini 3.5 Flash and 3.1 Flash-Lite
    for model_name in ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            return res.text.strip()
        except Exception as err:
            print(f"Model {model_name} failed: {err}")
            continue
            
    return f"{signal_type} trigger active at ₹{price} (RSI: {rsi})."

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_agent():
    # Expanded high-volume Nifty 50 watchlist
    watchlist = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
        "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS",
        "BAJFINANCE.NS", "MARUTI.NS", "AXISBANK.NS", "SUNPHARMA.NS", "KOTAKBANK.NS"
    ]
    
    detected_signals = []
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")

    for ticker in watchlist:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y", interval="1d")
            if df.empty or len(df) < 200:
                continue

            # 1. Moving Averages
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            
            # 2. RSI
            df['RSI'] = calculate_rsi(df)

            # 3. MACD
            df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
            df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = df['EMA_12'] - df['EMA_26']
            df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

            # 4. Volume Spike Check
            df['Vol_Avg20'] = df['Volume'].rolling(20).mean()

            price = round(float(df['Close'].iloc[-1]), 2)
            ema200 = round(float(df['EMA_200'].iloc[-1]), 2)
            rsi = round(float(df['RSI'].iloc[-1]), 2)
            macd_val = round(float(df['MACD'].iloc[-1]), 2)
            signal_val = round(float(df['Signal_Line'].iloc[-1]), 2)
            vol_spike = bool(df['Volume'].iloc[-1] > (1.2 * df['Vol_Avg20'].iloc[-1]))

            macd_status = "Bullish Crossover" if macd_val > signal_val else "Bearish"
            indicators_text = f"MACD: {macd_status} | Vol: {'🔥 High' if vol_spike else 'Normal'}"

            signal_type = None

            # BUY CRITERIA: RSI pullback (< 50) + Uptrend (Above 200 EMA) + Bullish MACD
            if rsi < 50 and price > ema200 and macd_val > signal_val:
                signal_type = "BUY"
            
            # EXIT / PROFIT-TAKING CRITERIA: RSI Overbought (> 68) or Breakdown below 200 EMA
            elif rsi > 68 or (price < ema200 and rsi < 42):
                signal_type = "EXIT"

            if signal_type:
                analysis = generate_ai_analysis(ticker, price, rsi, ema200, signal_type, macd_status)
                signal_entry = {
                    "ticker": ticker,
                    "type": signal_type,
                    "price": price,
                    "rsi": rsi,
                    "indicators": indicators_text,
                    "time": current_time,
                    "analysis": analysis
                }
                detected_signals.append(signal_entry)

                icon = "🟢" if signal_type == "BUY" else "🔴"
                msg = (
                    f"{icon} <b>AI {signal_type} SIGNAL: {ticker}</b>\n\n"
                    f"<b>Price:</b> ₹{price} | <b>RSI:</b> {rsi}\n"
                    f"<b>Setup:</b> {indicators_text}\n\n"
                    f"<b>AI Thesis:</b>\n{analysis}"
                )
                send_telegram_alert(msg)
                print(f"Dispatched {signal_type} alert for {ticker}")

        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    with open("signals.json", "w") as f:
        json.dump({"last_updated": current_time, "signals": detected_signals}, f, indent=2)

if __name__ == "__main__":
    run_agent()
