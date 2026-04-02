import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import requests
import feedparser
import re
from datetime import datetime, timedelta
from supabase import create_client
import json

# ================================
# KONFIGURASI HALAMAN
# ================================
st.set_page_config(page_title="IHSG Fund Manager Suite", layout="wide")
st.title("🏦 Dashboard Fund Manager IHSG")
st.markdown("Analisis Makro | Fundamental | Teknikal | Sentimen | Risiko | Rekomendasi")

# ================================
# KONEKSI SUPABASE
# ================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================================
# 1. DATA MAKRO EKONOMI
# ================================
@st.cache_data(ttl=3600)  # cache 1 jam
def get_macro_data():
    """Ambil data makro: BI rate, inflasi, kurs IDR/USD, IHSG global (S&P 500)"""
    data = {}
    try:
        # Kurs IDR/USD dari yfinance
        usd_idr = yf.Ticker("IDR=X")
        hist = usd_idr.history(period="1d")
        data['kurs'] = hist['Close'].iloc[-1] if not hist.empty else 15500
    except:
        data['kurs'] = 15500
    
    try:
        # S&P 500 sebagai perbandingan global
        spy = yf.Ticker("^GSPC")
        spy_hist = spy.history(period="5d")
        if not spy_hist.empty:
            data['sp500'] = spy_hist['Close'].iloc[-1]
            data['sp500_change'] = ((spy_hist['Close'].iloc[-1] - spy_hist['Close'].iloc[-2]) / spy_hist['Close'].iloc[-2]) * 100
        else:
            data['sp500'] = 4500
            data['sp500_change'] = 0
    except:
        data['sp500'] = 4500
        data['sp500_change'] = 0
    
    # Data BI rate dan inflasi (sumber sementara, nanti bisa upgrade)
    # Karena scraping BI/BPS rawan, kita pakai nilai default update manual via secrets nanti
    # Untuk sementara, kita bisa ambil dari API free atau hardcode dulu
    # Saya gunakan nilai perkiraan terbaru (Anda bisa ganti di secrets nanti)
    data['bi_rate'] = st.secrets.get("BI_RATE", 5.75)   # default
    data['inflation'] = st.secrets.get("INFLATION", 3.2) # default
    
    # Kondisi makro: hijau jika kondusif
    kondusif = (data['bi_rate'] <= 6.0 and data['inflation'] <= 4.0)
    data['macro_status'] = "Kondusif (Risk On)" if kondusif else "Kurang Kondusif (Risk Off)"
    data['macro_color'] = "green" if kondusif else "red"
    
    return data

# ================================
# 2. DATA FUNDAMENTAL AGREGAT IHSG (Proksi dari LQ45)
# ================================
@st.cache_data(ttl=86400)  # cache 1 hari
def get_fundamental_ihsg():
    """Hitung rata-rata PER, PBV, DY dari saham LQ45 sebagai proksi IHSG"""
    # Daftar saham LQ45 (simbol + .JK)
    lq45 = ["BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "ADRO.JK", "UNVR.JK", "ICBP.JK", "CPIN.JK", "GGRM.JK"]
    per_list = []
    pbv_list = []
    dy_list = []
    
    for code in lq45:
        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            if 'trailingPE' in info and info['trailingPE']:
                per_list.append(info['trailingPE'])
            if 'priceToBook' in info and info['priceToBook']:
                pbv_list.append(info['priceToBook'])
            if 'dividendYield' in info and info['dividendYield']:
                dy_list.append(info['dividendYield'] * 100)
        except:
            continue
    
    avg_per = sum(per_list)/len(per_list) if per_list else 15
    avg_pbv = sum(pbv_list)/len(pbv_list) if pbv_list else 2.0
    avg_dy = sum(dy_list)/len(dy_list) if dy_list else 2.5
    
    # Penilaian valuasi
    if avg_per < 14:
        valuasi = "Murah"
        valuasi_color = "green"
    elif avg_per < 18:
        valuasi = "Wajar"
        valuasi_color = "orange"
    else:
        valuasi = "Mahal"
        valuasi_color = "red"
    
    return {
        'per': round(avg_per, 2),
        'pbv': round(avg_pbv, 2),
        'dy': round(avg_dy, 2),
        'valuasi': valuasi,
        'valuasi_color': valuasi_color
    }

# ================================
# 3. DATA TEKNIKAL IHSG & BANDARMOLOGY
# ================================
@st.cache_data(ttl=600)
def get_ihsg_data():
    """Ambil data harga IHSG dari Yahoo Finance"""
    ticker = yf.Ticker("^JKSE")
    df = ticker.history(period="1mo", interval="1d")
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def calculate_obv(df):
    """Hitung On-Balance Volume"""
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    return obv

def detect_bandarmology(df):
    """Deteksi potensi bandar: lonjakan volume, divergensi"""
    if len(df) < 6:
        return {"signal": "Data kurang", "desc": "Butuh minimal 6 hari data"}
    avg_vol = df['volume'].tail(6).head(5).mean()
    latest_vol = df['volume'].iloc[-1]
    vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1
    
    # Divergensi sederhana: harga naik tipis tapi volume besar => akumulasi
    price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    if vol_ratio > 1.5 and price_change < 0.5 and price_change > 0:
        signal = "Akumulasi (Divergensi Bullish)"
        desc = f"Harga naik tipis ({price_change:.2f}%) tapi volume melonjak {vol_ratio:.1f}x, potensi akumulasi bandar."
    elif vol_ratio > 2:
        signal = "Lonjakan Volume Ekstrim"
        desc = f"Volume {vol_ratio:.1f}x rata-rata, waspada aksi bandar."
    elif vol_ratio > 1.5:
        signal = "Peningkatan Volume"
        desc = f"Volume meningkat {vol_ratio:.1f}x, perhatikan pergerakan selanjutnya."
    else:
        signal = "Normal"
        desc = "Volume normal, belum terdeteksi anomali."
    return {"signal": signal, "desc": desc, "vol_ratio": vol_ratio}

# ================================
# 4. SENTIMEN & BERITA (RSS scraping)
# ================================
@st.cache_data(ttl=1800)
def get_news_sentiment():
    """Ambil berita dari RSS Kontan dan CNBC Indonesia, beri label sentimen sederhana"""
    news_items = []
    # RSS Kontan untuk IHSG
    try:
        feed = feedparser.parse("https://insight.kontan.co.id/rss/ekonomi")
        for entry in feed.entries[:5]:
            title = entry.title
            # Analisis sentimen sederhana berdasarkan kata kunci
            positif = ["naik", "menguat", "positif", "optimis", "cerah", "lonjak", "rekor"]
            negatif = ["turun", "melemah", "negatif", "waswas", "tekan", "risiko", "inflasi"]
            score = 0
            for word in positif:
                if word in title.lower():
                    score += 1
            for word in negatif:
                if word in title.lower():
                    score -= 1
            sentiment = "Positif" if score > 0 else ("Negatif" if score < 0 else "Netral")
            news_items.append({"title": title, "source": "Kontan", "sentiment": sentiment})
    except:
        pass
    
    # RSS CNBC Indonesia
    try:
        feed = feedparser.parse("https://www.cnbcindonesia.com/news/rss")
        for entry in feed.entries[:5]:
            title = entry.title
            positif = ["naik", "menguat", "positif", "optimis", "cerah", "lonjak"]
            negatif = ["turun", "melemah", "negatif", "waswas", "tekan"]
            score = 0
            for word in positif:
                if word in title.lower():
                    score += 1
            for word in negatif:
                if word in title.lower():
                    score -= 1
            sentiment = "Positif" if score > 0 else ("Negatif" if score < 0 else "Netral")
            news_items.append({"title": title, "source": "CNBC Indonesia", "sentiment": sentiment})
    except:
        pass
    
    # Hitung agregat sentimen
    if news_items:
        pos_count = sum(1 for n in news_items if n['sentiment'] == 'Positif')
        neg_count = sum(1 for n in news_items if n['sentiment'] == 'Negatif')
        net_sentiment = pos_count - neg_count
        sentiment_score = net_sentiment  # bisa -5 sampai +5
        sentiment_desc = "Positif" if sentiment_score > 0 else ("Negatif" if sentiment_score < 0 else "Netral")
    else:
        sentiment_score = 0
        sentiment_desc = "Tidak ada data"
    
    return {"news": news_items, "score": sentiment_score, "desc": sentiment_desc}

# ================================
# 5. MANAJEMEN RISIKO & PORTOFOLIO SEDERHANA
# ================================
def portfolio_management():
    st.sidebar.subheader("📒 Portofolio Pribadi")
    with st.sidebar.form("portfolio_form"):
        action = st.selectbox("Aksi", ["Beli", "Jual"])
        amount = st.number_input("Jumlah lot (1 lot = 100 saham)", min_value=1, step=1)
        price = st.number_input("Harga per saham", min_value=50, step=50)
        submitted = st.form_submit_button("Catat Transaksi")
        if submitted:
            # Simpan ke Supabase (tabel portfolio)
            try:
                supabase.table('portfolio').insert({
                    'tanggal': datetime.now().isoformat(),
                    'aksi': action,
                    'lot': amount,
                    'harga': price
                }).execute()
                st.sidebar.success("Tersimpan")
            except:
                st.sidebar.error("Gagal simpan. Pastikan tabel 'portfolio' sudah dibuat.")
    
    # Tampilkan posisi saat ini (hitung dari Supabase)
    try:
        resp = supabase.table('portfolio').select('*').execute()
        if resp.data:
            df_port = pd.DataFrame(resp.data)
            st.sidebar.write("**Riwayat Transaksi**")
            st.sidebar.dataframe(df_port[['tanggal', 'aksi', 'lot', 'harga']].tail(5))
    except:
        st.sidebar.info("Belum ada data portofolio")

# ================================
# 6. REKOMENDASI KEPUTUSAN (Integrasi semua faktor)
# ================================
def generate_recommendation(macro, fundamental, bandarmology, sentiment, price_change):
    """Gabungkan semua faktor jadi rekomendasi dengan alasan"""
    score = 0
    reasons = []
    
    # Makro
    if "Kondusif" in macro['macro_status']:
        score += 1
        reasons.append("✓ Makro kondusif (suku bunga stabil, inflasi rendah)")
    else:
        score -= 1
        reasons.append("✗ Makro kurang kondusif")
    
    # Fundamental
    if fundamental['valuasi'] == "Murah":
        score += 1
        reasons.append(f"✓ Valuasi murah (PER {fundamental['per']})")
    elif fundamental['valuasi'] == "Wajar":
        score += 0
        reasons.append(f"→ Valuasi wajar (PER {fundamental['per']})")
    else:
        score -= 1
        reasons.append(f"✗ Valuasi mahal (PER {fundamental['per']})")
    
    # Teknikal/Bandarmology
    if "Akumulasi" in bandarmology['signal']:
        score += 2
        reasons.append(f"✓ {bandarmology['desc']}")
    elif "Lonjakan" in bandarmology['signal']:
        score += 1
        reasons.append(f"→ {bandarmology['desc']}")
    else:
        reasons.append(f"→ {bandarmology['desc']}")
    
    # Sentimen
    if sentiment['score'] > 0:
        score += 1
        reasons.append(f"✓ Sentimen positif (skor {sentiment['score']})")
    elif sentiment['score'] < 0:
        score -= 1
        reasons.append(f"✗ Sentimen negatif (skor {sentiment['score']})")
    else:
        reasons.append("→ Sentimen netral")
    
    # Perubahan harga recent
    if price_change > 1:
        score += 0.5
        reasons.append(f"✓ Harga naik {price_change:.2f}% dalam sehari")
    elif price_change < -1:
        score -= 0.5
        reasons.append(f"✗ Harga turun {price_change:.2f}%")
    
    # Keputusan final
    if score >= 2:
        rec = "AKUMULASI / BELI"
        rec_color = "green"
    elif score >= 0:
        rec = "HOLD / TUNGGU"
        rec_color = "orange"
    elif score >= -1:
        rec = "KURANGI POSISI"
        rec_color = "red"
    else:
        rec = "DISTRIBUSI / KELUAR"
        rec_color = "darkred"
    
    return rec, rec_color, score, reasons

# ================================
# MAIN DASHBOARD
# ================================

# Ambil semua data
macro = get_macro_data()
fund = get_fundamental_ihsg()
df_ihsg = get_ihsg_data()
band = detect_bandarmology(df_ihsg) if not df_ihsg.empty else {"signal": "Tidak ada data", "desc": "", "vol_ratio": 1}
sentiment = get_news_sentiment()

# Hitung perubahan harga terbaru
if not df_ihsg.empty and len(df_ihsg) > 1:
    last_price = df_ihsg['close'].iloc[-1]
    prev_price = df_ihsg['close'].iloc[-2]
    price_change = ((last_price - prev_price) / prev_price) * 100
    ihsg_current = last_price
else:
    price_change = 0
    ihsg_current = 0

# Rekomendasi
recommendation, rec_color, score, reasons = generate_recommendation(macro, fund, band, sentiment, price_change)

# Tampilan Header
col1, col2, col3 = st.columns(3)
col1.metric("IHSG", f"{ihsg_current:,.0f}" if ihsg_current else "N/A", f"{price_change:.2f}%")
col2.metric("Status Makro", macro['macro_status'], delta_color="off")
col3.metric("Rekomendasi", recommendation, delta_color="off")

st.markdown(f"<h3 style='color:{rec_color}'>📌 {recommendation}</h3>", unsafe_allow_html=True)
st.markdown("**Alasan:**")
for r in reasons:
    st.write(r)

# Layout 2 kolom untuk kartu
colA, colB = st.columns(2)

with colA:
    st.subheader("📈 Makro Ekonomi")
    st.write(f"BI Rate: **{macro['bi_rate']}%**")
    st.write(f"Inflasi: **{macro['inflation']}%**")
    st.write(f"Kurs IDR/USD: **{macro['kurs']:,.0f}**")
    st.write(f"S&P 500: **{macro['sp500']:.0f}** ({macro['sp500_change']:.2f}%)")
    
    st.subheader("🏭 Fundamental IHSG (Proksi LQ45)")
    st.write(f"PER: **{fund['per']}** ({fund['valuasi']})")
    st.write(f"PBV: **{fund['pbv']}**")
    st.write(f"Dividend Yield: **{fund['dy']}%**")

with colB:
    st.subheader("📊 Teknikal & Bandarmology")
    if not df_ihsg.empty:
        fig = go.Figure(data=[go.Candlestick(x=df_ihsg['timestamp'], open=df_ihsg['open'], high=df_ihsg['high'], low=df_ihsg['low'], close=df_ihsg['close'])])
        fig.update_layout(height=350, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"**{band['signal']}**")
        st.write(band['desc'])
    else:
        st.warning("Data IHSG belum tersedia. Klik tombol di sidebar untuk ambil data.")
    
    st.subheader("📰 Sentimen & Berita")
    st.write(f"Skor Sentimen: **{sentiment['score']}** ({sentiment['desc']})")
    for news in sentiment['news'][:3]:
        st.write(f"- {news['title'][:60]}... *({news['sentiment']})*")

# Sidebar untuk kontrol dan portofolio
with st.sidebar:
    st.header("⚙️ Kontrol Data")
    if st.button("🔄 Ambil Data IHSG Baru"):
        with st.spinner("Mengambil data..."):
            new_data = get_ihsg_data()
            if not new_data.empty:
                for _, row in new_data.iterrows():
                    supabase.table('ihsg_prices').upsert({
                        'timestamp': row['timestamp'].isoformat(),
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': int(row['volume'])
                    }).execute()
                st.success("Data IHSG tersimpan!")
            else:
                st.error("Gagal ambil data.")
    
    portfolio_management()
    
    st.markdown("---")
    st.caption("Aplikasi ini untuk tujuan edukasi dan analisis pribadi. Keputusan investasi tetap pada pengguna.")

# ================================
# INISIALISASI TABEL DATABASE (Jika belum ada)
# ================================
# Untuk keamanan, kita tidak buat tabel otomatis via kode. Anda perlu buat manual di Supabase:
# Tabel ihsg_prices (lihat sebelumnya)
# Tabel portfolio: (id serial, tanggal timestamptz, aksi text, lot int, harga float)
