import streamlit as st
import qrcode
from io import BytesIO

# ページ全体のレイアウトをワイド（画面横幅いっぱい）に設定
st.set_page_config(page_title="日付QRコード生成アプリ", layout="wide")

st.title("日付QRコード生成アプリ")

# 画面を3つのカラムに分割
col1, col2, col3 = st.columns(3)

# QRコード生成ヘルパー関数
def generate_qr(text):
    if not text:
        return None
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Streamlit表示用にバイトストリームへ変換
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# --- 左側（1つ目） ---
with col1:
    st.subheader("1つ目")
    date_1 = st.text_input("日付を入力 (例: 8/22)", value="8/22", key="date1")
    if date_1:
        qr_bytes_1 = generate_qr(date_1)
        st.image(qr_bytes_1, caption=f"QR: {date_1}", use_container_width=True)

# --- 真ん中（2つ目） ---
with col2:
    st.subheader("2つ目")
    date_2 = st.text_input("日付を入力 (例: 8/23)", value="8/23", key="date2")
    if date_2:
        qr_bytes_2 = generate_qr(date_2)
        st.image(qr_bytes_2, caption=f"QR: {date_2}", use_container_width=True)

# --- 右側（3つ目） ---
with col3:
    st.subheader("3つ目")
    date_3 = st.text_input("日付を入力 (例: 8/24)", value="8/24", key="date3")
    if date_3:
        qr_bytes_3 = generate_qr(date_3)
        st.image(qr_bytes_3, caption=f"QR: {date_3}", use_container_width=True)
