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

def generate_ai_analysis(ticker, price, rsi, ema200):
    if not client:
        return "RSI oversold momentum rebound setup."
    prompt = (
        f"Analyze this swing setup for {ticker}: Price: ₹{price}, RSI: {rsi}, 200 EMA: ₹{ema200}. "
        f"Provide a 2-sentence trading assessment covering momentum status and recommended Stop Loss level."
    )
    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            return res.text.strip()
        except Exception:
            continue
    return f"Momentum setup active with RSI at {rsi}."

def run_agent():
    watchlist = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS"]
    detected_signals = []
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")

    for ticker in watchlist:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y", interval="1d")
            if df.empty or len(df) < 200:
                continue

            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            price = round(float(df['Close'].iloc[-1]), 2)
            ema = round(float(df['EMA_200'].iloc[-1]), 2)
            rsi = round(float(df['RSI'].iloc[-1]), 2)

            # Signal trigger threshold
            if rsi < 55:
                analysis = generate_ai_analysis(ticker, price, rsi, ema)
                signal_entry = {
                    "ticker": ticker,
                    "price": price,
                    "rsi": rsi,
                    "time": current_time,
                    "analysis": analysis
                }
                detected_signals.append(signal_entry)

                msg = (
                    f"🤖 <b>AI SIGNAL: {ticker}</b>\n\n"
                    f"<b>Price:</b> ₹{price} | <b>RSI:</b> {rsi}\n\n"
                    f"<b>Thesis:</b>\n{analysis}"
                )
                send_telegram_alert(msg)
                print(f"Dispatched alert for {ticker}")
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    # Save to JSON file for your frontend website to display
    with open("signals.json", "w") as f:
        json.dump({"last_updated": current_time, "signals": detected_signals}, f, indent=2)

if __name__ == "__main__":
    run_agent()
