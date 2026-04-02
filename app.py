import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from supabase import create_client
from defeatbeta import Ticker
import time

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="IHSG Fund Manager Dashboard", layout="wide")
st.title("📊 Dashboard Analisis IHSG - ala Fund Manager")

# --- KONEKSI KE SUPABASE ---
# GANTI nilai di bawah dengan URL dan ANON KEY dari project Supabase Anda!
SUPABASE_URL = "https://xxxxxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIs..." 
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNGSI UNTUK AMBIL DATA DARI DEFEATBETA ---
@st.cache_data(ttl=600) # Data akan di-cache selama 10 menit
def fetch_ihsg_data():
    """Ambil data IHSG dari Defeatbeta API"""
    ihsg = Ticker('^JKSE')
    # Ambil data 30 hari terakhir dengan interval 1 hari
    data = ihsg.history(period="1mo", interval="1d")
    
    if data.empty:
        return pd.DataFrame()
    
    # Reset index agar timestamp menjadi kolom
    data = data.reset_index()
    # Sesuaikan nama kolom
    data.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    return data

# --- FUNGSI UNTUK SIMPAN DATA KE SUPABASE ---
def save_to_supabase(data):
    """Simpan data ke tabel ihsg_prices di Supabase"""
    for _, row in data.iterrows():
        supabase.table('ihsg_prices').upsert({
            'timestamp': row['timestamp'].isoformat(),
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': int(row['volume'])
        }).execute()
    st.success(f"✅ Data berhasil disimpan ke Supabase! Total {len(data)} baris.")

# --- SIDEBAR UNTUK KONTROL ---
with st.sidebar:
    st.header("⚙️ Kontrol Data")
    if st.button("🔄 Ambil & Simpan Data IHSG Terbaru"):
        with st.spinner("Mengambil data dari Defeatbeta API..."):
            df_new = fetch_ihsg_data()
            if not df_new.empty:
                save_to_supabase(df_new)
            else:
                st.error("Gagal mengambil data. Coba lagi nanti.")

# --- MAIN DASHBOARD: MENAMPILKAN DATA DARI SUPABASE ---
st.header("📈 Grafik Pergerakan IHSG")

# Ambil data dari Supabase
response = supabase.table('ihsg_prices').select('*').order('timestamp', desc=False).execute()

if response.data:
    df = pd.DataFrame(response.data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # --- CANDLESTICK CHART ---
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close']
    )])
    
    fig.update_layout(
        title="IHSG - Candlestick Chart",
        yaxis_title="Harga",
        xaxis_title="Tanggal",
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # --- METRIK SEDERHANA ---
    last_price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2]
    change = last_price - prev_price
    change_pct = (change / prev_price) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Harga Terakhir", f"{last_price:,.2f}", f"{change_pct:.2f}%")
    col2.metric("Tertinggi Hari Ini", f"{df['high'].iloc[-1]:,.2f}")
    col3.metric("Terendah Hari Ini", f"{df['low'].iloc[-1]:,.2f}")
    
    # --- DETEKSI LONJAKAN VOLUME (SEDERHANA) ---
    st.subheader("🔍 Deteksi Aksi Bandar (Sederhana)")
    # Hitung rata-rata volume 5 hari terakhir
    avg_volume = df['volume'].tail(6).head(5).mean()
    latest_volume = df['volume'].iloc[-1]
    
    if latest_volume > 2 * avg_volume:
        st.warning(f"⚠️ **Potensi Aksi Bandar!** Volume melonjak {latest_volume/avg_volume:.1f}x dari rata-rata.")
    else:
        st.info(f"Volume hari ini {latest_volume/avg_volume:.1f}x dari rata-rata 5 hari terakhir.")
        
else:
    st.info("💡 Data IHSG masih kosong. Silakan klik tombol 'Ambil & Simpan Data IHSG Terbaru' di sidebar.")
