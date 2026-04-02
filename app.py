import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import requests
import feedparser
from datetime import datetime
from supabase import create_client
import wbgapi as wb

# ================================
# KONFIGURASI HALAMAN
# ================================
st.set_page_config(page_title="IHSG Fund Manager Suite", layout="wide")
st.title("🏦 Dashboard Fund Manager IHSG")
st.markdown("Analisis Makro | Fundamental | Teknikal | Sentimen | Risiko | Rekomendasi")

# ================================
# KONEKSI SUPABASE
# ================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets Supabase tidak ditemukan.")
    supabase = None

# ================================
# 1. DATA MAKRO EKONOMI
# ================================
@st.cache_data(ttl=3600)
def get_macro_data():
    data = {}
    # Kurs IDR/USD
    try:
        usd_idr = yf.Ticker("IDR=X")
        hist = usd_idr.history(period="1d")
        data['kurs'] = hist['Close'].iloc[-1] if not hist.empty else 15500
    except:
        data['kurs'] = 15500
    # S&P 500
    try:
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
    # Inflasi dari World Bank
    try:
        inflasi_df = wb.data.DataFrame('FP.CPI.TOTL', 'idn', mrv=1)
        data['inflation'] = float(inflasi_df.iloc[0, 0]) if not inflasi_df.empty else 3.2
    except:
        data['inflation'] = 3.2
    # Suku bunga riil dari World Bank
    try:
        suku_df = wb.data.DataFrame('FR.INR.RINR', 'idn', mrv=1)
        data['bi_rate'] = float(suku_df.iloc[0, 0]) if not suku_df.empty else 5.75
    except:
        data['bi_rate'] = 5.75
    # Status makro
    kondusif = (data['bi_rate'] <= 6.0 and data['inflation'] <= 4.0)
    data['macro_status'] = "Kondusif (Risk On)" if kondusif else "Kurang Kondusif (Risk Off)"
    return data

# ================================
# 2. DATA FUNDAMENTAL (Proksi LQ45)
# ================================
@st.cache_data(ttl=86400)
def get_fundamental_ihsg():
    lq45 = ["BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "ADRO.JK", "UNVR.JK", "ICBP.JK", "CPIN.JK", "GGRM.JK"]
    per_list, pbv_list, dy_list = [], [], []
    for code in lq45:
        try:
            info = yf.Ticker(code).info
            if info.get('trailingPE'): per_list.append(info['trailingPE'])
            if info.get('priceToBook'): pbv_list.append(info['priceToBook'])
            if info.get('dividendYield'): dy_list.append(info['dividendYield'] * 100)
        except:
            continue
    avg_per = sum(per_list)/len(per_list) if per_list else 15
    avg_pbv = sum(pbv_list)/len(pbv_list) if pbv_list else 2.0
    avg_dy = sum(dy_list)/len(dy_list) if dy_list else 2.5
    if avg_per < 14: valuasi, warna = "Murah", "green"
    elif avg_per < 18: valuasi, warna = "Wajar", "orange"
    else: valuasi, warna = "Mahal", "red"
    return {'per': round(avg_per,2), 'pbv': round(avg_pbv,2), 'dy': round(avg_dy,2), 'valuasi': valuasi, 'warna': warna}

# ================================
# 3. DATA IHSG (ROBUST)
# ================================
@st.cache_data(ttl=600)
def get_ihsg_data():
    ticker = yf.Ticker("^JKSE")
    df = ticker.history(period="1mo", interval="1d")
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    # Mapping kolom otomatis
    col_map = {'Date':'timestamp', 'Open':'open', 'High':'high', 'Low':'low', 'Close':'close', 'Volume':'volume'}
    available = {k:v for k,v in col_map.items() if k in df.columns}
    if len(available) < 6:
        # Coba lowercase
        df.columns = [c.lower() for c in df.columns]
        col_map_lower = {'date':'timestamp', 'open':'open', 'high':'high', 'low':'low', 'close':'close', 'volume':'volume'}
        available = {k:v for k,v in col_map_lower.items() if k in df.columns}
    if len(available) < 6:
        return pd.DataFrame()
    df = df[list(available.keys())]
    df.rename(columns=available, inplace=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['volume'] = df['volume'].fillna(0).astype(int)
    return df

def detect_bandarmology(df):
    if len(df) < 6:
        return {"signal": "Data kurang", "desc": "Butuh minimal 6 hari", "ratio": 1}
    avg_vol = df['volume'].tail(6).head(5).mean()
    latest_vol = df['volume'].iloc[-1]
    ratio = latest_vol / avg_vol if avg_vol > 0 else 1
    price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    if ratio > 1.5 and 0 < price_change < 0.5:
        signal = "Akumulasi (Divergensi Bullish)"
        desc = f"Harga naik tipis ({price_change:.2f}%) tapi volume melonjak {ratio:.1f}x"
    elif ratio > 2:
        signal = "Lonjakan Volume Ekstrim"
        desc = f"Volume {ratio:.1f}x rata-rata, waspada aksi bandar"
    elif ratio > 1.5:
        signal = "Peningkatan Volume"
        desc = f"Volume meningkat {ratio:.1f}x"
    else:
        signal = "Normal"
        desc = "Volume normal"
    return {"signal": signal, "desc": desc, "ratio": ratio}

# ================================
# 4. SENTIMEN BERITA
# ================================
@st.cache_data(ttl=1800)
def get_news_sentiment():
    news_items = []
    for url, source in [("https://insight.kontan.co.id/rss/ekonomi", "Kontan"),
                        ("https://www.cnbcindonesia.com/news/rss", "CNBC Indonesia")]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.title
                pos = ["naik","menguat","positif","optimis","cerah","lonjak"]
                neg = ["turun","melemah","negatif","waswas","tekan"]
                score = sum(1 for w in pos if w in title.lower()) - sum(1 for w in neg if w in title.lower())
                sentiment = "Positif" if score>0 else ("Negatif" if score<0 else "Netral")
                news_items.append({"title": title[:80], "source": source, "sentiment": sentiment})
        except:
            continue
    if news_items:
        pos = sum(1 for n in news_items if n['sentiment']=='Positif')
        neg = sum(1 for n in news_items if n['sentiment']=='Negatif')
        score = pos - neg
        desc = "Positif" if score>0 else ("Negatif" if score<0 else "Netral")
    else:
        score, desc = 0, "Tidak ada data"
    return {"news": news_items, "score": score, "desc": desc}

# ================================
# 5. PORTOFOLIO
# ================================
def portfolio_ui():
    st.sidebar.subheader("📒 Portofolio")
    with st.sidebar.form("porto"):
        aksi = st.selectbox("Aksi", ["Beli", "Jual"])
        lot = st.number_input("Lot (1 lot=100)", 1, step=1)
        harga = st.number_input("Harga per saham", 50, step=50)
        if st.form_submit_button("Catat") and supabase:
            supabase.table('portfolio').insert({'tanggal': datetime.now().isoformat(), 'aksi': aksi, 'lot': lot, 'harga': harga}).execute()
            st.sidebar.success("Tersimpan")
    if supabase:
        try:
            resp = supabase.table('portfolio').select('*').execute()
            if resp.data:
                dfp = pd.DataFrame(resp.data)
                st.sidebar.dataframe(dfp[['tanggal','aksi','lot','harga']].tail(3))
        except:
            st.sidebar.info("Tabel portfolio belum dibuat")

# ================================
# 6. REKOMENDASI
# ================================
def rekomendasi(macro, fund, band, sent, pct):
    skor = 0
    alasan = []
    # Makro
    if "Kondusif" in macro['macro_status']:
        skor += 1
        alasan.append("✓ Makro kondusif")
    else:
        skor -= 1
        alasan.append("✗ Makro kurang kondusif")
    # Fundamental
    if fund['valuasi'] == "Murah":
        skor += 1
        alasan.append(f"✓ Valuasi murah (PER {fund['per']})")
    elif fund['valuasi'] == "Wajar":
        alasan.append(f"→ Valuasi wajar (PER {fund['per']})")
    else:
        skor -= 1
        alasan.append(f"✗ Valuasi mahal (PER {fund['per']})")
    # Bandarmology
    if "Akumulasi" in band['signal']:
        skor += 2
        alasan.append(f"✓ {band['desc']}")
    elif "Lonjakan" in band['signal']:
        skor += 1
        alasan.append(f"→ {band['desc']}")
    else:
        alasan.append(f"→ {band['desc']}")
    # Sentimen
    if sent['score'] > 0:
        skor += 1
        alasan.append("✓ Sentimen positif")
    elif sent['score'] < 0:
        skor -= 1
        alasan.append("✗ Sentimen negatif")
    else:
        alasan.append("→ Sentimen netral")
    # Perubahan harga
    if pct > 1:
        skor += 0.5
        alasan.append(f"✓ Harga naik {pct:.2f}%")
    elif pct < -1:
        skor -= 0.5
        alasan.append(f"✗ Harga turun {pct:.2f}%")
    # Keputusan
    if skor >= 2: rec, warna = "AKUMULASI / BELI", "green"
    elif skor >= 0: rec, warna = "HOLD / TUNGGU", "orange"
    elif skor >= -1: rec, warna = "KURANGI POSISI", "red"
    else: rec, warna = "DISTRIBUSI / KELUAR", "darkred"
    return rec, warna, skor, alasan

# ================================
# MAIN DASHBOARD
# ================================
macro = get_macro_data()
fund = get_fundamental_ihsg()
df_ihsg = get_ihsg_data()
band = detect_bandarmology(df_ihsg) if not df_ihsg.empty else {"signal":"Tidak ada data","desc":"","ratio":1}
sent = get_news_sentiment()

if not df_ihsg.empty and len(df_ihsg) > 1:
    last = df_ihsg['close'].iloc[-1]
    prev = df_ihsg['close'].iloc[-2]
    pct = (last - prev)/prev*100
    ihsg_val = last
else:
    pct = 0
    ihsg_val = 0

rec, warna, skor, alasan = rekomendasi(macro, fund, band, sent, pct)

col1, col2, col3 = st.columns(3)
col1.metric("IHSG", f"{ihsg_val:,.0f}" if ihsg_val else "N/A", f"{pct:.2f}%")
col2.metric("Makro", macro['macro_status'])
col3.metric("Rekomendasi", rec)

st.markdown(f"<h3 style='color:{warna}'>📌 {rec}</h3>", unsafe_allow_html=True)
st.markdown("**Alasan:**")
for a in alasan:
    st.write(a)

colA, colB = st.columns(2)
with colA:
    st.subheader("📈 Makro")
    st.write(f"BI Rate (riil): **{macro['bi_rate']:.2f}%**")
    st.write(f"Inflasi: **{macro['inflation']:.2f}%**")
    st.write(f"Kurs IDR/USD: **{macro['kurs']:,.0f}**")
    st.write(f"S&P 500: **{macro['sp500']:.0f}** ({macro['sp500_change']:.2f}%)")
    st.subheader("🏭 Fundamental")
    st.write(f"PER: **{fund['per']}** ({fund['valuasi']})")
    st.write(f"PBV: **{fund['pbv']}**")
    st.write(f"Dividend Yield: **{fund['dy']}%**")
with colB:
    st.subheader("📊 Teknikal & Bandarmology")
    if not df_ihsg.empty:
        fig = go.Figure(data=[go.Candlestick(x=df_ihsg['timestamp'], open=df_ihsg['open'], high=df_ihsg['high'], low=df_ihsg['low'], close=df_ihsg['close'])])
        fig.update_layout(height=350, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"**{band['signal']}**")
        st.write(band['desc'])
    else:
        st.warning("Data IHSG kosong. Klik tombol di sidebar.")
    st.subheader("📰 Sentimen")
    st.write(f"Skor: **{sent['score']}** ({sent['desc']})")
    for n in sent['news'][:3]:
        st.write(f"- {n['title']} *({n['sentiment']})*")

with st.sidebar:
    st.header("⚙️ Kontrol")
    if st.button("🔄 Ambil Data IHSG"):
        with st.spinner("..."):
            new = get_ihsg_data()
            if not new.empty and supabase:
                for _, row in new.iterrows():
                    supabase.table('ihsg_prices').upsert({
                        'timestamp': row['timestamp'].isoformat(),
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': int(row['volume'])
                    }).execute()
                st.success("Tersimpan")
            else:
                st.error("Gagal")
    portfolio_ui()
    st.caption("Analisis pribadi | Bukan saran investasi")
