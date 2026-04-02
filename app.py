import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import feedparser
import requests
from datetime import datetime
from supabase import create_client
import wbgapi as wb

# ============================================================
# KONFIGURASI HALAMAN
# ============================================================
st.set_page_config(page_title="Fund Manager Dashboard - IDX", layout="wide")
st.title("🏦 Fund Manager Dashboard - Indonesia")
st.markdown("**31 Poin Analisis:** Makro | Fundamental | Teknikal & Bandarmology | Aliran Dana & Sentimen | Risiko & Portofolio | Rekomendasi")

# ============================================================
# KONEKSI SUPABASE
# ============================================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    supabase = None
    st.warning("Supabase tidak terhubung, beberapa fitur tidak tersedia.")

# ============================================================
# DAFTAR SAHAM IDX (Fallback jika API gagal)
# ============================================================
@st.cache_data(ttl=86400)
def get_all_stocks():
    """Mengambil daftar saham dari API IDX, fallback ke daftar statis jika gagal."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.idx.co.id/",
        "Origin": "https://www.idx.co.id"
    }
    url = "https://www.idx.co.id/primary/ListedCompany/GetStock?length=1000"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and 'data' in data and 'results' in data['data']:
                stocks = data['data']['results']
                df = pd.DataFrame(stocks)
                df = df[['KodeEmiten', 'NamaEmiten']]
                df.columns = ['Kode', 'Nama']
                df['Ticker'] = df['Kode'] + '.JK'
                return df
    except Exception as e:
        st.warning(f"Gagal mengambil daftar saham dari API IDX: {e}")
    
    # Fallback: daftar statis (LQ45 + beberapa saham likuid)
    static_stocks = [
        ("AALI", "Astra Agro Lestari"), ("ADRO", "Adaro Energy"), ("AKRA", "AKR Corporindo"),
        ("AMMN", "Amman Mineral"), ("ANTM", "Aneka Tambang"), ("ARTO", "Bank Jago"),
        ("ASII", "Astra International"), ("BBCA", "Bank Central Asia"), ("BBRI", "Bank Rakyat Indonesia"),
        ("BBTN", "Bank Tabungan Negara"), ("BMRI", "Bank Mandiri"), ("BRPT", "Barito Pacific"),
        ("BSDE", "Bumi Serpong Damai"), ("BTPS", "Bank BTPN Syariah"), ("BUKA", "Bukalapak"),
        ("CPIN", "Charoen Pokphand"), ("ERAA", "Erajaya Swasembada"), ("EXCL", "XL Axiata"),
        ("FREN", "Smartfren Telecom"), ("GGRM", "Gudang Garam"), ("ICBP", "Indofood CBP"),
        ("INCO", "Vale Indonesia"), ("INDF", "Indofood Sukses Makmur"), ("INKP", "Indah Kiat Pulp"),
        ("INTP", "Indocement Tunggal Prakarsa"), ("ISAT", "Indosat"), ("JPFA", "Japfa Comfeed"),
        ("JSMR", "Jasa Marga"), ("KLBF", "Kalbe Farma"), ("LINK", "Link Net"),
        ("MDKA", "Merdeka Copper Gold"), ("MEDC", "Medco Energi"), ("MIKA", "Mitra Keluarga"),
        ("MNCN", "Media Nusantara Citra"), ("MTEL", "Dayamitra Telekomunikasi"), ("PGAS", "Perusahaan Gas Negara"),
        ("PTBA", "Bukit Asam"), ("PTPP", "PP Presisi"), ("SIDO", "Industri Jamu Sido Muncul"),
        ("SILO", "Siloam Hospitals"), ("SMGR", "Semen Indonesia"), ("SMRA", "Summarecon Agung"),
        ("SRTG", "Saratoga Investama"), ("TBIG", "Tower Bersama"), ("TECH", "Indointernet"),
        ("TINS", "Timah"), ("TLKM", "Telkom Indonesia"), ("TOWR", "Sarana Menara Nusantara"),
        ("TPIA", "Chandra Asri"), ("UNTR", "United Tractors"), ("UNVR", "Unilever Indonesia"),
        ("WIKA", "Wijaya Karya"), ("WSKT", "Waskita Karya")
    ]
    df = pd.DataFrame(static_stocks, columns=['Kode', 'Nama'])
    df['Ticker'] = df['Kode'] + '.JK'
    st.info("Menggunakan daftar saham statis (LQ45 + tambahan). Untuk saham lain, silakan input manual.")
    return df

# ============================================================
# 1. DATA MAKRO EKONOMI (sama seperti sebelumnya)
# ============================================================
@st.cache_data(ttl=3600)
def get_macro_data():
    data = {}
    try:
        usd_idr = yf.Ticker("IDR=X")
        hist = usd_idr.history(period="1d")
        data['kurs'] = hist['Close'].iloc[-1] if not hist.empty else 15500
        data['kurs_trend'] = "Menguat" if hist['Close'].iloc[-1] < hist['Close'].iloc[-2] else "Melemah"
    except:
        data['kurs'] = 15500
        data['kurs_trend'] = "N/A"
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
    # Data dari secrets
    data['fiscal_deficit'] = st.secrets.get("FISCAL_DEFICIT", 2.92)
    data['debt_to_gdp'] = st.secrets.get("DEBT_TO_GDP", 39.0)
    data['credit_rating'] = st.secrets.get("CREDIT_RATING", "BBB (stable)")
    try:
        bond_url = "https://id.investing.com/rates-bonds/indonesia-10-year-bond-yield"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(bond_url, headers=headers, timeout=10)
        if response.status_code == 200:
            import re
            match = re.search(r'data-usd="([\d.]+)"', response.text)
            data['bond_yield'] = float(match.group(1)) if match else 6.59
        else:
            data['bond_yield'] = 6.59
    except:
        data['bond_yield'] = 6.59
    try:
        gdp_df = wb.data.DataFrame('NY.GDP.MKTP.KD.ZG', 'idn', mrv=1)
        data['gdp_growth'] = float(gdp_df.iloc[0, 0]) if not gdp_df.empty else 5.0
    except:
        data['gdp_growth'] = 5.0
    kondusif = (data['bi_rate'] <= 6.0 and data['inflation'] <= 4.0 and data['gdp_growth'] >= 5.0)
    data['macro_status'] = "Kondusif (Risk On)" if kondusif else "Kurang Kondusif (Risk Off)"
    return data

# ============================================================
# 2. DATA SAHAM INDIVIDUAL (Fundamental & Teknikal)
# ============================================================
@st.cache_data(ttl=86400)
def get_stock_fundamental(stock_code):
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

@st.cache_data(ttl=600)
def get_stock_data(stock_code):
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
    if len(df) < 6:
        return {"signal": "Data kurang", "desc": "Butuh minimal 6 hari", "ratio": 1, "obv_trend": "Netral"}
    avg_vol = df['volume'].tail(6).head(5).mean()
    latest_vol = df['volume'].iloc[-1]
    ratio = latest_vol / avg_vol if avg_vol > 0 else 1
    price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    obv = calculate_obv(df)
    obv_trend = "Bullish" if obv[-1] > obv[-5] else "Bearish" if obv[-1] < obv[-5] else "Netral"
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
# 3. IHSG & SENTIMEN & FOREIGN FLOW
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

@st.cache_data(ttl=3600)
def get_foreign_flow():
    try:
        # Menggunakan data dummy karena API IDX sering berubah, tapi ini bisa di-upgrade
        # Alternatif: scraping dari halaman idx.co.id/primary/DataTrading
        return {"net_flow": 0, "status": "N/A"}
    except:
        return {"net_flow": 0, "status": "N/A"}

# ============================================================
# 4. PORTOFOLIO & REKOMENDASI
# ============================================================
def portfolio_management():
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
            pass

def generate_recommendation(macro, fundamental, band, sentiment, foreign_flow, price_change):
    score = 0
    reasons = []
    if "Kondusif" in macro['macro_status']:
        score += 1
        reasons.append("✓ Makro kondusif")
    else:
        score -= 1
        reasons.append("✗ Makro kurang kondusif")
    if fundamental['valuasi'] == "Murah":
        score += 1
        reasons.append(f"✓ Valuasi murah (PER {fundamental['per']})")
    elif fundamental['valuasi'] == "Wajar":
        reasons.append(f"→ Valuasi wajar (PER {fundamental['per']})")
    else:
        score -= 1
        reasons.append(f"✗ Valuasi mahal (PER {fundamental['per']})")
    if "Akumulasi" in band['signal']:
        score += 2
        reasons.append(f"✓ {band['desc']}")
    elif "Lonjakan" in band['signal']:
        score += 1
        reasons.append(f"→ {band['desc']}")
    else:
        reasons.append(f"→ {band['desc']}")
    if sentiment['score'] > 0:
        score += 1
        reasons.append("✓ Sentimen positif")
    elif sentiment['score'] < 0:
        score -= 1
        reasons.append("✗ Sentimen negatif")
    else:
        reasons.append("→ Sentimen netral")
    if foreign_flow['net_flow'] > 0:
        score += 1
        reasons.append("✓ Aliran asing positif")
    elif foreign_flow['net_flow'] < 0:
        score -= 1
        reasons.append("✗ Aliran asing negatif")
    if price_change > 1:
        score += 0.5
        reasons.append(f"✓ Harga naik {price_change:.2f}%")
    elif price_change < -1:
        score -= 0.5
        reasons.append(f"✗ Harga turun {price_change:.2f}%")
    if score >= 2:
        rec, warna = "AKUMULASI / BELI", "green"
    elif score >= 0:
        rec, warna = "HOLD / TUNGGU", "orange"
    elif score >= -1:
        rec, warna = "KURANGI POSISI", "red"
    else:
        rec, warna = "DISTRIBUSI / KELUAR", "darkred"
    return rec, warna, max(0, min(score, 10)), reasons

# ============================================================
# MAIN DASHBOARD
# ============================================================
macro = get_macro_data()
stocks_df = get_all_stocks()
if not stocks_df.empty:
    stock_codes = stocks_df['Kode'].tolist()
    stock_names = dict(zip(stocks_df['Kode'], stocks_df['Nama']))
else:
    stock_codes = ["BBCA", "BBRI", "TLKM"]
    stock_names = {"BBCA":"Bank Central Asia", "BBRI":"Bank Rakyat Indonesia", "TLKM":"Telkom"}

with st.sidebar:
    st.header("⚙️ Kontrol")
    selected_stock = st.selectbox("Pilih Kode Saham", stock_codes, format_func=lambda x: f"{x} - {stock_names.get(x, '')}")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    portfolio_management()
    st.caption("Analisis pribadi | Bukan saran investasi")

fund = get_stock_fundamental(selected_stock)
df_stock = get_stock_data(selected_stock)
band = detect_bandarmology(df_stock) if not df_stock.empty else {"signal":"Data kurang","desc":"","ratio":1,"obv_trend":"Netral"}
sentiment = get_news_sentiment()
foreign_flow = get_foreign_flow()
if not df_stock.empty and len(df_stock) > 1:
    last_price = df_stock['close'].iloc[-1]
    prev_price = df_stock['close'].iloc[-2]
    price_change = (last_price - prev_price)/prev_price*100
    stock_current = last_price
else:
    price_change = 0
    stock_current = 0

rec, rec_color, score, reasons = generate_recommendation(macro, fund, band, sentiment, foreign_flow, price_change)

# Header
col1, col2, col3, col4 = st.columns(4)
col1.metric(f"{selected_stock}", f"{stock_current:,.0f}" if stock_current else "N/A", f"{price_change:.2f}%")
col2.metric("Makro", macro['macro_status'])
col3.metric("Rekomendasi", rec)
col4.metric("Skor", f"{score}/10")
st.markdown(f"<h3 style='color:{rec_color}'>📌 {rec}</h3>", unsafe_allow_html=True)
with st.expander("Lihat alasan keputusan", expanded=True):
    for r in reasons:
        st.write(r)

# Dua kolom utama dengan scroll agar teks tidak terpotong
colA, colB = st.columns(2, gap="large")
with colA:
    with st.container(height=400):
        st.subheader("📈 Makro Ekonomi")
        st.write(f"PDB: **{macro['gdp_growth']:.1f}%** | Inflasi: **{macro['inflation']:.2f}%**")
        st.write(f"BI Rate: **{macro['bi_rate']:.2f}%** | Defisit fiskal: **{macro['fiscal_deficit']:.2f}%**")
        st.write(f"Utang/PDB: **{macro['debt_to_gdp']:.1f}%** | Peringkat: **{macro['credit_rating']}**")
        st.write(f"Kurs: **{macro['kurs']:,.0f}** ({macro['kurs_trend']}) | Obligasi 10th: **{macro['bond_yield']:.2f}%**")
        st.write(f"S&P500: **{macro['sp500']:.0f}** ({macro['sp500_change']:.2f}%)")
    with st.container(height=400):
        st.subheader("🏭 Fundamental Saham")
        st.write(f"PER: **{fund['per']}** ({fund['valuasi']}) | PBV: **{fund['pbv']}**")
        st.write(f"Dividend Yield: **{fund['dy']:.2f}%** | Market Cap: **{fund['market_cap']/1e12:.2f}T IDR**")
        st.write(f"EPS: **{fund['eps']:.0f}**")
    with st.container(height=400):
        st.subheader("💰 Aliran Dana & Sentimen")
        st.write(f"Net Flow Asing: **{foreign_flow['status']}**")
        st.write(f"Skor Sentimen Berita: **{sentiment['score']}** ({sentiment['desc']})")
        for news in sentiment['news'][:3]:
            st.write(f"- {news['title'][:70]}... *({news['sentiment']})*")

with colB:
    st.subheader("📊 Teknikal & Bandarmology")
    if not df_stock.empty:
        fig = go.Figure(data=[go.Candlestick(x=df_stock['timestamp'], open=df_stock['open'], high=df_stock['high'], low=df_stock['low'], close=df_stock['close'])])
        fig.update_layout(height=350, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"**OBV Trend:** {band['obv_trend']}")
        if len(df_stock) >= 20:
            sup = df_stock['low'].tail(20).min()
            res = df_stock['high'].tail(20).max()
            st.write(f"Support (20h): **{sup:,.0f}** | Resistance: **{res:,.0f}**")
        st.write(f"**Sinyal:** {band['signal']}")
        st.write(band['desc'])
    else:
        st.warning("Data saham kosong.")

# IHSG sebagai pembanding
st.subheader("📊 IHSG (Pembanding Pasar)")
df_ihsg = get_ihsg_data()
if not df_ihsg.empty:
    fig_ihsg = go.Figure(data=[go.Candlestick(x=df_ihsg['timestamp'], open=df_ihsg['open'], high=df_ihsg['high'], low=df_ihsg['low'], close=df_ihsg['close'])])
    fig_ihsg.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_ihsg, use_container_width=True)

# Simpan ke Supabase (opsional)
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
