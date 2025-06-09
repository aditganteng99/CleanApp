import streamlit as st
import os
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from textblob import TextBlob
import requests
import re

EMAIL_PENGIRIM = "m.aldek.saputra08@gmail.com"
EMAIL_PENERIMA = "m.aldek.saputra08@gmail.com"
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

st.set_page_config(page_title="Saham Otomatis Harian", layout="wide")
st.title("📈 Aplikasi Screening Saham IDX Otomatis + Sentimen")

@st.cache_data
def get_all_idx_tickers():
    try:
        url = "https://raw.githubusercontent.com/dudung/daftar-saham-IDX/main/data/saham-idx.txt"
        res = requests.get(url)
        tickers = re.findall(r'\b[A-Z]{4,5}\b', res.text)
        return [ticker + ".JK" for ticker in tickers]
    except:
        return ["BBCA.JK", "ANTM.JK", "TLKM.JK"]

def cek_sentimen_google(ticker):
    try:
        url = f"https://news.google.com/rss/search?q={ticker}+stock+site:kontan.co.id&hl=id"
        r = requests.get(url)
        items = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
        headlines = " ".join(items[:5])
        blob = TextBlob(headlines)
        return blob.sentiment.polarity
    except:
        return 0

def kirim_email(body, subject="Sinyal Saham Harian"):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_PENGIRIM
        msg["To"] = EMAIL_PENERIMA
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_PENGIRIM, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Email Error:", e)
        return False

def screening_idx(dengan_sentimen=False):
    tickers = get_all_idx_tickers()
    hasil = []
    modal = 10_000_000

    progress = st.progress(0)
    st.write(f"Mulai screening {len(tickers)} saham...")

    for i, kode in enumerate(tickers):
        try:
            ticker_obj = yf.Ticker(kode)
            df = ticker_obj.history(period="7d", interval="1d")
            df_intra = ticker_obj.history(period="1d", interval="5m")

            if df.empty or df_intra.empty:
                st.write(f"Data kosong untuk {kode}, dilewati.")
                continue

            harga = df_intra["Close"].iloc[-1]
            open_now = df_intra["Open"].iloc[-1]
            ma5 = df["Close"].rolling(5).mean().iloc[-1]
            ma20 = df["Close"].rolling(20).mean().iloc[-1]

            gain = df["Close"].diff().where(lambda x: x > 0, 0).rolling(14).mean().iloc[-1]
            loss = df["Close"].diff().where(lambda x: x < 0, 0).abs().rolling(14).mean().iloc[-1]

            if loss == 0:
                rsi = 100
            else:
                rsi = 100 - (100 / (1 + (gain / loss)))

            avg_vol = df["Volume"].rolling(5).mean().iloc[-1]

            kondisi = (harga > open_now and ma5 > ma20 and rsi < 60 and df["Volume"].iloc[-1] > avg_vol)
            if kondisi:
                lot = max(int(modal // (harga * 100)), 1)
                tp = harga * 1.03
                sl = harga * 0.98
                est_profit = int((tp - harga) * lot * 100)
                est_loss = int((harga - sl) * lot * 100)

                sentimen = 1
                if dengan_sentimen:
                    sentimen = cek_sentimen_google(kode.replace(".JK", ""))
                    st.write(f"Sentimen untuk {kode}: {sentimen}")

                if not dengan_sentimen or sentimen > 0:
                    hasil.append({
                        "Kode": kode,
                        "Harga": round(harga, 2),
                        "Lot": lot,
                        "TP": round(tp, 2),
                        "SL": round(sl, 2),
                        "Profit": est_profit,
                        "Loss": est_loss,
                        "RSI": round(rsi, 2),
                        "Sentimen": round(sentimen, 2) if dengan_sentimen else "-"
                    })
                else:
                    st.write(f"{kode} disaring karena sentimen <= 0.")
            else:
                st.write(f"{kode} tidak memenuhi kondisi screening.")

        except Exception as e:
            st.write(f"Error pada ticker {kode}: {e}")

        progress.progress((i + 1) / len(tickers))

    st.write(f"Jumlah saham lolos filter: {len(hasil)}")

    if not hasil:
        st.warning("❌ Tidak ada saham yang lolos filter hari ini.")
        return pd.DataFrame()

    df = pd.DataFrame(hasil)

    if "Profit" not in df.columns:
        st.error("Data hasil tidak memiliki kolom 'Profit'.")
        return df

    df = df.sort_values("Profit", ascending=False).head(5)

    st.dataframe(df)
    st.download_button("⬇️ Download CSV", data=df.to_csv(index=False).encode(), file_name="sinyal.csv")

    body = f"""📈 Sinyal Saham:

{df.to_string(index=False)}
"""
    if st.button("📧 Kirim ke Email"):
        if kirim_email(body):
            st.success("📬 Email berhasil dikirim.")
        else:
            st.error("Gagal kirim email.")

    return df


col1, col2 = st.columns(2)
with col1:
    if st.button("🔍 Screening IDX Otomatis"):
        screening_idx(dengan_sentimen=False)
with col2:
    if st.button("🔎 Screening IDX + Sentimen Pasar"):
        screening_idx(dengan_sentimen=True)

if "IS_CRON" in st.query_params:
    screening_idx(dengan_sentimen=True)
