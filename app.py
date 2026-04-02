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

# --- FUNGSI AMBIL DATA IHSG (Robust) ---
@st.cache_data(ttl=600)
def fetch_ihsg_data():
    """Ambil data IHSG dari Yahoo Finance, dengan penanganan kolom otomatis"""
    ticker = yf.Ticker("^JKSE")
    data = ticker.history(period="1mo", interval="1d")
    
    if data.empty:
        return pd.DataFrame()
    
    # Reset index agar tanggal menjadi kolom
    data = data.reset_index()
    
    # Kolom yang diharapkan: Date, Open, High, Low, Close, Volume
    # Tapi yfinance kadang tambah Dividends, Stock Splits, Adj Close
    # Kita pilih kolom yang kita butuhkan saja
    required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    available_cols = [col for col in required_cols if col in data.columns]
    
    if len(available_cols) < 6:
        st.error("Data tidak lengkap. Coba lagi nanti.")
        return pd.DataFrame()
    
    data = data[available_cols]
    data.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    # Bersihkan data: pastikan volume integer
    data['volume'] = data['volume'].fillna(0).astype(int)
    
    return data

# --- FUNGSI SIMPAN KE SUPABASE ---
def save_to_supabase(data):
    for _, row in data.iterrows():
        supabase.table('ihsg_prices').upsert({
            'timestamp': row['timestamp'].isoformat(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row['volume'])
        }).execute()
    st.success(f"✅ Data berhasil disimpan! Total {len(data)} baris.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Kontrol Data")
    if st.button("🔄 Ambil & Simpan Data IHSG Terbaru"):
        with st.spinner("Mengambil data dari Yahoo Finance..."):
            df_new = fetch_ihsg_data()
            if not df_new.empty:
                save_to_supabase(df_new)
            else:
                st.error("Gagal mengambil data. Coba lagi nanti.")

# --- MAIN DASHBOARD ---
st.header("📈 Grafik Pergerakan IHSG")

response = supabase.table('ihsg_prices').select('*').order('timestamp', desc=False).execute()

if response.data:
    df = pd.DataFrame(response.data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close']
    )])
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)
    
    # Metrik sederhana
    last_price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2] if len(df) > 1 else last_price
    change_pct = ((last_price - prev_price) / prev_price) * 100 if prev_price != 0 else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Harga Terakhir", f"{last_price:,.2f}", f"{change_pct:.2f}%")
    col2.metric("Tertinggi", f"{df['high'].iloc[-1]:,.2f}")
    col3.metric("Terendah", f"{df['low'].iloc[-1]:,.2f}")
    
    # Deteksi lonjakan volume (bandarmology sederhana)
    st.subheader("🔍 Deteksi Aksi Bandar")
    if len(df) >= 6:
        avg_volume = df['volume'].tail(6).head(5).mean()
        latest_volume = df['volume'].iloc[-1]
        ratio = latest_volume / avg_volume if avg_volume > 0 else 1
        if ratio > 2:
            st.warning(f"⚠️ **Potensi Aksi Bandar!** Volume melonjak {ratio:.1f}x dari rata-rata.")
        else:
            st.info(f"Volume normal ({ratio:.1f}x dari rata-rata 5 hari)")
    else:
        st.info("Belum cukup data untuk deteksi lonjakan volume.")
else:
    st.info("💡 Data IHSG masih kosong. Klik tombol 'Ambil & Simpan Data IHSG Terbaru' di sidebar.")
