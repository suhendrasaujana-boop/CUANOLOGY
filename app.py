import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import feedparser
import requests
from datetime import datetime, timedelta
from supabase import create_client
import wbgapi as wb
import time

# ============================================================
# 1. KONFIGURASI HALAMAN & KONEKSI SUPABASE
# ============================================================
st.set_page_config(page_title="Fund Manager Dashboard - IDX", layout="wide")
st.title("🏦 Fund Manager Dashboard - Indonesia")
st.markdown("**31 Poin Analisis:** Makro | Fundamental Pasar | Teknikal & Bandarmology | Aliran Dana & Sentimen | Risiko & Portofolio | Rekomendasi")

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets Supabase tidak ditemukan. Silakan atur di Streamlit Secrets.")
    supabase = None

# ============================================================
# 2. DATA MAKRO EKONOMI (Poin 1-8)
# ============================================================
@st.cache_data(ttl=3600)
def get_macro_data():
    data = {}
    
    # 1. Kurs IDR/USD (poin 7)
    try:
        usd_idr = yf.Ticker("IDR=X")
        hist = usd_idr.history(period="1d")
        data['kurs'] = hist['Close'].iloc[-1] if not hist.empty else 15500
        data['kurs_trend'] = "Menguat" if hist['Close'].iloc[-1] < hist['Close'].iloc[-2] else "Melemah"
    except:
        data['kurs'] = 15500
        data['kurs_trend'] = "N/A"
    
    # 2. S&P 500 (poin 8, sebagai perbandingan global)
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
    
    # 3. Inflasi (poin 2) & Suku bunga riil (poin 3) dari World Bank
    try:
        inflasi_df = wb.data.DataFrame('FP.CPI.TOTL', 'idn', mrv=1)
        data['inflation'] = float(inflasi_df.iloc[0, 0]) if not inflasi_df.empty else 3.2
    except:
        data['inflation'] = 3.2
    
    try:
        suku_df = wb.data.DataFrame('FR.INR.RINR', 'idn', mrv=1)
        data['bi_rate'] = float(suku_df.iloc[0, 0]) if not suku_df.empty else 5.75
    except:
        data['bi_rate'] = 5.75
    
    # 4. Defisit fiskal (poin 4) & Rasio utang/PDB (poin 5) – manual input via secrets (update berkala)
    data['fiscal_deficit'] = st.secrets.get("FISCAL_DEFICIT", 2.92)  # default 2.92% dari PDB
    data['debt_to_gdp'] = st.secrets.get("DEBT_TO_GDP", 39.0)        # default 39% dari PDB
    
    # 5. Peringkat kredit (poin 6) – manual input via secrets
    data['credit_rating'] = st.secrets.get("CREDIT_RATING", "BBB (stable)")
    
    # 6. Imbal hasil obligasi 10 tahun (poin 8) dari Investing.com
    try:
        # Menggunakan API tidak resmi, fallback ke nilai default jika gagal
        bond_url = "https://id.investing.com/rates-bonds/indonesia-10-year-bond-yield"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(bond_url, headers=headers, timeout=10)
        if response.status_code == 200:
            # parsing sederhana (harga yield di halaman)
            import re
            match = re.search(r'data-usd="([\d.]+)"', response.text)
            if match:
                data['bond_yield'] = float(match.group(1))
            else:
                data['bond_yield'] = 6.59
        else:
            data['bond_yield'] = 6.59
    except:
        data['bond_yield'] = 6.59
    
    # 7. Pertumbuhan PDB (poin 1) dari World Bank
    try:
        gdp_df = wb.data.DataFrame('NY.GDP.MKTP.KD.ZG', 'idn', mrv=1)
        data['gdp_growth'] = float(gdp_df.iloc[0, 0]) if not gdp_df.empty else 5.0
    except:
        data['gdp_growth'] = 5.0
    
    # Status makro
    kondusif = (data['bi_rate'] <= 6.0 and data['inflation'] <= 4.0 and data['gdp_growth'] >= 5.0)
    data['macro_status'] = "Kondusif (Risk On)" if kondusif else "Kurang Kondusif (Risk Off)"
    return data

# ============================================================
# 3. DAFTAR SEMUA EMITEN IDX (Poin - sumber data)
# ============================================================
@st.cache_data(ttl=86400)
def get_all_stocks():
    """
    Mengambil daftar semua saham yang terdaftar di BEI.
    Menggunakan API resmi idx.co.id.
    """
    url = "https://www.idx.co.id/primary/ListedCompany/GetStock?length=10000"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and 'data' in data and 'results' in data['data']:
            stocks = data['data']['results']
            df = pd.DataFrame(stocks)
            df = df[['KodeEmiten', 'NamaEmiten']]
            df.columns = ['Kode', 'Nama']
            df['Ticker'] = df['Kode'] + '.JK'
            return df
        else:
            st.error("Struktur data dari API tidak dikenali.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Gagal mengambil daftar saham: {e}")
        return pd.DataFrame()

# ============================================================
# 4. DATA FUNDAMENTAL SAHAM INDIVIDUAL (Poin 9-13)
# ============================================================
@st.cache_data(ttl=86400)
def get_stock_fundamental(stock_code):
    """Ambil fundamental saham individual: PER, PBV, DY, Market Cap, EPS, dll"""
    ticker = yf.Ticker(stock_code + ".JK")
    info = ticker.info
    data = {
        'per': info.get('trailingPE', 0),
        'pbv': info.get('priceToBook', 0),
        'dy': info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0,
        'market_cap': info.get('marketCap', 0),
        'eps': info.get('trailingEps', 0),
        'name': info.get('longName', stock_code)
    }
    
    # Valuasi (poin 10-12)
    if data['per'] == 0:
        valuasi = "N/A"
    elif data['per'] < 14:
        valuasi = "Murah"
    elif data['per'] < 18:
        valuasi = "Wajar"
    else:
        valuasi = "Mahal"
    data['valuasi'] = valuasi
    return data

# ============================================================
# 5. DATA TEKNIKAL SAHAM (Poin 14-19) + BANDARMOLOGY (Poin 16-17)
# ============================================================
@st.cache_data(ttl=600)
def get_stock_data(stock_code):
    """Ambil data harga saham individual"""
    ticker = yf.Ticker(stock_code + ".JK")
    df = ticker.history(period="1mo", interval="1d")
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    if 'date' not in df.columns:
        df = df.rename(columns={'index': 'date'})
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['volume'] = df['volume'].fillna(0).astype(int)
    return df

def calculate_obv(df):
    """Hitung On-Balance Volume (poin 15)"""
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
    """Deteksi potensi bandar: lonjakan volume, divergensi (poin 16-17)"""
    if len(df) < 6:
        return {"signal": "Data kurang", "desc": "Butuh minimal 6 hari", "ratio": 1, "obv_trend": "Netral"}
    
    avg_vol = df['volume'].tail(6).head(5).mean()
    latest_vol = df['volume'].iloc[-1]
    ratio = latest_vol / avg_vol if avg_vol > 0 else 1
    price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    
    # OBV Trend
    obv = calculate_obv(df)
    obv_trend = "Bullish" if obv[-1] > obv[-5] else "Bearish" if obv[-1] < obv[-5] else "Netral"
    
    # Divergensi (poin 17)
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
    return {"signal": signal, "desc": desc, "ratio": ratio, "obv_trend": obv_trend}

# ============================================================
# 6. DATA IHSG (Poin 9-13 untuk IHSG)
# ============================================================
@st.cache_data(ttl=600)
def get_ihsg_data():
    ticker = yf.Ticker("^JKSE")
    df = ticker.history(period="1mo", interval="1d")
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    if 'date' not in df.columns:
        df = df.rename(columns={'index': 'date'})
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

# ============================================================
# 7. SENTIMEN BERITA (Poin 20-23)
# ============================================================
@st.cache_data(ttl=1800)
def get_news_sentiment():
    """Ambil berita dari RSS, beri label sentimen sederhana (poin 20-23)"""
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

# ============================================================
# 8. ALIRAN DANA ASING (Poin 20-21) – Scraping dari IDX
# ============================================================
@st.cache_data(ttl=3600)
def get_foreign_flow():
    """Ambil net buy/sell asing dari IDX (poin 20)"""
    try:
        url = "https://www.idx.co.id/primary/DataTrading/GetDataTrading?length=1"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and 'data' in data and data['data']:
                latest = data['data'][0]
                foreign_buy = float(latest.get('ForeignBuy', 0))
                foreign_sell = float(latest.get('ForeignSell', 0))
                net_flow = foreign_buy - foreign_sell
                return {"net_flow": net_flow, "status": "Net Buy" if net_flow > 0 else "Net Sell"}
        return {"net_flow": 0, "status": "N/A"}
    except:
        return {"net_flow": 0, "status": "N/A"}

# ============================================================
# 9. MANAJEMEN PORTOFOLIO PRIBADI (Poin 24-28)
# ============================================================
def portfolio_management():
    st.sidebar.subheader("📒 Portofolio Pribadi")
    with st.sidebar.form("portfolio_form"):
        action = st.selectbox("Aksi", ["Beli", "Jual"])
        amount = st.number_input("Jumlah lot (1 lot = 100 saham)", min_value=1, step=1)
        price = st.number_input("Harga per saham", min_value=50, step=50)
        submitted = st.form_submit_button("Catat Transaksi")
        if submitted and supabase:
            supabase.table('portfolio').insert({
                'tanggal': datetime.now().isoformat(),
                'aksi': action,
                'lot': amount,
                'harga': price
            }).execute()
            st.sidebar.success("Tersimpan")
    
    if supabase:
        try:
            resp = supabase.table('portfolio').select('*').execute()
            if resp.data:
                df_port = pd.DataFrame(resp.data)
                st.sidebar.write("**Riwayat Transaksi**")
                st.sidebar.dataframe(df_port[['tanggal', 'aksi', 'lot', 'harga']].tail(5))
        except:
            st.sidebar.info("Tabel portfolio belum dibuat")

# ============================================================
# 10. REKOMENDASI KEPUTUSAN (Poin 29-31)
# ============================================================
def generate_recommendation(macro, fundamental, bandarmology, sentiment, foreign_flow, price_change, stock_code):
    """Gabungkan semua faktor jadi rekomendasi dengan alasan (poin 29-31)"""
    score = 0
    reasons = []
    
    # Makro (bobot 1)
    if "Kondusif" in macro['macro_status']:
        score += 1
        reasons.append("✓ Makro kondusif (BI rate stabil, inflasi rendah, GDP tumbuh)")
    else:
        score -= 1
        reasons.append("✗ Makro kurang kondusif")
    
    # Fundamental (bobot 1)
    if fundamental['valuasi'] == "Murah":
        score += 1
        reasons.append(f"✓ Valuasi murah (PER {fundamental['per']})")
    elif fundamental['valuasi'] == "Wajar":
        score += 0
        reasons.append(f"→ Valuasi wajar (PER {fundamental['per']})")
    else:
        score -= 1
        reasons.append(f"✗ Valuasi mahal (PER {fundamental['per']})")
    
    # Teknikal/Bandarmology (bobot 2)
    if "Akumulasi" in bandarmology['signal']:
        score += 2
        reasons.append(f"✓ {bandarmology['desc']}")
    elif "Lonjakan" in bandarmology['signal']:
        score += 1
        reasons.append(f"→ {bandarmology['desc']}")
    else:
        reasons.append(f"→ {bandarmology['desc']}")
    
    # Sentimen (bobot 1)
    if sentiment['score'] > 0:
        score += 1
        reasons.append(f"✓ Sentimen positif (skor {sentiment['score']})")
    elif sentiment['score'] < 0:
        score -= 1
        reasons.append(f"✗ Sentimen negatif (skor {sentiment['score']})")
    else:
        reasons.append("→ Sentimen netral")
    
    # Aliran dana asing (bobot 1)
    if foreign_flow['net_flow'] > 0:
        score += 1
        reasons.append(f"✓ Aliran asing positif (Net Buy {foreign_flow['net_flow']:,.0f})")
    elif foreign_flow['net_flow'] < 0:
        score -= 1
        reasons.append(f"✗ Aliran asing negatif (Net Sell {foreign_flow['net_flow']:,.0f})")
    
    # Perubahan harga (bobot 0.5)
    if price_change > 1:
        score += 0.5
        reasons.append(f"✓ Harga naik {price_change:.2f}% dalam sehari")
    elif price_change < -1:
        score -= 0.5
        reasons.append(f"✗ Harga turun {price_change:.2f}%")
    
    # Rekomendasi final (poin 29)
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
    
    # Skor keputusan (poin 31)
    score_normalized = min(max(score, 0), 10)  # range 0-10
    return rec, rec_color, score_normalized, reasons

# ============================================================
# 11. MAIN DASHBOARD
# ============================================================

# Ambil data makro
macro = get_macro_data()

# Sidebar: Pilih saham
with st.sidebar:
    st.header("⚙️ Kontrol & Seleksi Saham")
    
    # Ambil daftar semua saham
    all_stocks_df = get_all_stocks()
    if not all_stocks_df.empty:
        stock_list = all_stocks_df['Kode'].tolist()
        selected_stock = st.selectbox("Pilih Kode Saham", stock_list)
        stock_name = all_stocks_df[all_stocks_df['Kode'] == selected_stock]['Nama'].values[0]
        st.write(f"**Nama:** {stock_name}")
    else:
        selected_stock = st.text_input("Masukkan Kode Saham (contoh: BBCA)", "BBCA")
    
    # Tombol refresh data
    if st.button("🔄 Refresh Data Saham"):
        st.cache_data.clear()
        st.rerun()
    
    # Portfolio management
    portfolio_management()
    
    st.caption("Analisis pribadi | Bukan saran investasi")

# Ambil data fundamental dan teknikal untuk saham terpilih
fund = get_stock_fundamental(selected_stock)
df_stock = get_stock_data(selected_stock)
band = detect_bandarmology(df_stock) if not df_stock.empty else {"signal": "Data kurang", "desc": "", "ratio": 1, "obv_trend": "Netral"}
sentiment = get_news_sentiment()
foreign_flow = get_foreign_flow()

# Hitung perubahan harga terbaru
if not df_stock.empty and len(df_stock) > 1:
    last_price = df_stock['close'].iloc[-1]
    prev_price = df_stock['close'].iloc[-2]
    price_change = ((last_price - prev_price) / prev_price) * 100
    stock_current = last_price
else:
    price_change = 0
    stock_current = 0

# Rekomendasi
rec, rec_color, score, reasons = generate_recommendation(macro, fund, band, sentiment, foreign_flow, price_change, selected_stock)

# Tampilan Header
col1, col2, col3, col4 = st.columns(4)
col1.metric(f"{selected_stock}", f"{stock_current:,.0f}" if stock_current else "N/A", f"{price_change:.2f}%")
col2.metric("Status Makro", macro['macro_status'])
col3.metric("Rekomendasi", rec)
col4.metric("Skor Keputusan", f"{score}/10")

st.markdown(f"<h3 style='color:{rec_color}'>📌 {rec}</h3>", unsafe_allow_html=True)
st.markdown("**Alasan:**")
for r in reasons:
    st.write(r)

# Layout 2 kolom untuk detail
colA, colB = st.columns(2)

with colA:
    st.subheader("📈 Makro Ekonomi")
    st.write(f"Pertumbuhan PDB: **{macro['gdp_growth']:.1f}%**")
    st.write(f"Inflasi: **{macro['inflation']:.2f}%**")
    st.write(f"Suku bunga BI: **{macro['bi_rate']:.2f}%**")
    st.write(f"Defisit fiskal: **{macro['fiscal_deficit']:.2f}% dari PDB**")
    st.write(f"Rasio utang/PDB: **{macro['debt_to_gdp']:.1f}%**")
    st.write(f"Peringkat kredit: **{macro['credit_rating']}**")
    st.write(f"Kurs IDR/USD: **{macro['kurs']:,.0f}** ({macro['kurs_trend']})")
    st.write(f"Imbal hasil obligasi 10 tahun: **{macro['bond_yield']:.2f}%**")
    st.write(f"S&P 500: **{macro['sp500']:.0f}** ({macro['sp500_change']:.2f}%)")
    
    st.subheader("🏭 Fundamental Saham")
    st.write(f"PER: **{fund['per']}** ({fund['valuasi']})")
    st.write(f"PBV: **{fund['pbv']}**")
    st.write(f"Dividend Yield: **{fund['dy']:.2f}%**")
    st.write(f"Market Cap: **{fund['market_cap']/1e12:.2f}T IDR**")
    st.write(f"EPS: **{fund['eps']:.0f}**")
    
    st.subheader("💰 Aliran Dana & Sentimen")
    st.write(f"Net Flow Asing: **{foreign_flow['status']}** ({foreign_flow['net_flow']:,.0f})")
    st.write(f"Skor Sentimen Berita: **{sentiment['score']}** ({sentiment['desc']})")
    for news in sentiment['news'][:3]:
        st.write(f"- {news['title'][:60]}... *({news['sentiment']})*")

with colB:
    st.subheader("📊 Teknikal & Bandarmology")
    if not df_stock.empty:
        # Candlestick chart
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock['timestamp'],
            open=df_stock['open'],
            high=df_stock['high'],
            low=df_stock['low'],
            close=df_stock['close']
        )])
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        # OBV line
        obv = calculate_obv(df_stock)
        st.write(f"**OBV Trend:** {band['obv_trend']}")
        
        # Support & Resistance (poin 18 - sederhana)
        if len(df_stock) >= 20:
            support = df_stock['low'].tail(20).min()
            resistance = df_stock['high'].tail(20).max()
            st.write(f"Support (20 hari): **{support:,.0f}** | Resistance (20 hari): **{resistance:,.0f}**")
        
        # Volume Profile (poin 19 - sederhana)
        vol_profile = df_stock.groupby(pd.cut(df_stock['close'], bins=10))['volume'].sum()
        st.write("**Volume Profile (10 level harga):**")
        st.dataframe(vol_profile.reset_index().rename(columns={'close': 'Harga Range', 'volume': 'Volume'}))
        
        st.write(f"**Sinyal Bandarmology:** {band['signal']}")
        st.write(band['desc'])
    else:
        st.warning("Data saham kosong. Coba refresh atau pilih saham lain.")

# IHSG sebagai pembanding
st.subheader("📊 IHSG (Pembanding Pasar)")
df_ihsg = get_ihsg_data()
if not df_ihsg.empty:
    fig_ihsg = go.Figure(data=[go.Candlestick(
        x=df_ihsg['timestamp'],
        open=df_ihsg['open'],
        high=df_ihsg['high'],
        low=df_ihsg['low'],
        close=df_ihsg['close']
    )])
    fig_ihsg.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_ihsg, use_container_width=True)
else:
    st.info("Data IHSG tidak tersedia.")

# Simpan data ke Supabase (opsional)
if supabase and not df_stock.empty:
    for _, row in df_stock.iterrows():
        supabase.table('stock_prices').upsert({
            'code': selected_stock,
            'timestamp': row['timestamp'].isoformat(),
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': int(row['volume'])
        }).execute()
