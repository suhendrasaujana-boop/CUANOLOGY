import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
import yfinance as yf

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="IHSG Fund Manager Dashboard", layout="wide")
st.title("📊 Dashboard Analisis IHSG - ala Fund Manager")

# --- KONEKSI KE SUPABASE ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNGSI AMBIL DATA IHSG ---
@st.cache_data(ttl=600)
def fetch_ihsg_data():
    ticker = yf.Ticker("^JKSE")
    data = ticker.history(period="1mo", interval="1d")
    if data.empty:
        return pd.DataFrame()
    data = data.reset_index()
    data.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    return data

# --- FUNGSI SIMPAN KE SUPABASE ---
def save_to_supabase(data):
    for _, row in data.iterrows():
        supabase.table('ihsg_prices').upsert({
            'timestamp': row['timestamp'].isoformat(),
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': int(row['volume'])
        }).execute()
    st.success(f"✅ Tersimpan {len(data)} baris.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Kontrol Data")
    if st.button("🔄 Ambil & Simpan Data IHSG"):
        with st.spinner("Mengambil data..."):
            df_new = fetch_ihsg_data()
            if not df_new.empty:
                save_to_supabase(df_new)
            else:
                st.error("Gagal ambil data.")

# --- MAIN DASHBOARD ---
st.header("📈 Grafik IHSG")
response = supabase.table('ihsg_prices').select('*').order('timestamp', desc=False).execute()

if response.data:
    df = pd.DataFrame(response.data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'], open=df['open'], high=df['high'],
        low=df['low'], close=df['close']
    )])
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)
    
    last = df['close'].iloc[-1]
    prev = df['close'].iloc[-2]
    pct = ((last - prev) / prev) * 100
    col1, col2, col3 = st.columns(3)
    col1.metric("Harga Terakhir", f"{last:,.2f}", f"{pct:.2f}%")
    col2.metric("Tertinggi", f"{df['high'].iloc[-1]:,.2f}")
    col3.metric("Terendah", f"{df['low'].iloc[-1]:,.2f}")
    
    avg_vol = df['volume'].tail(6).head(5).mean()
    latest_vol = df['volume'].iloc[-1]
    if latest_vol > 2 * avg_vol:
        st.warning(f"⚠️ Lonjakan volume! {latest_vol/avg_vol:.1f}x")
    else:
        st.info(f"Volume normal ({latest_vol/avg_vol:.1f}x)")
else:
    st.info("Klik tombol di sidebar.")
