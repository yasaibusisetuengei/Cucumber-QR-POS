import streamlit as st
import qrcode
from io import BytesIO

# ページ全体のレイアウトをワイド（画面横幅いっぱい）に設定
st.set_page_config(page_title="農作業記録QRコード生成アプリ", layout="wide")

st.title("農作業記録QRコード生成")

# カスタムCSSで画像下のキャプション（ラベル）の文字を大きく・太く表示する設定
st.markdown("""
    <style>
    .qr-label {
        font-size: 22px !important;
        font-weight: bold !important;
        text-align: center;
        color: #111111;
        margin-top: 8px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# シンプルなQRコード生成ヘルパー関数
def generate_qr(text):
    if not text:
        return None

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# 画面を4つのカラムに分割
col1, col2, col3, col4 = st.columns(4)

# --- 1列目: 収穫日 ---
with col1:
    st.subheader("収穫日")
    val_harvest = st.text_input("日付を入力", value="8/22", key="harvest")
    if val_harvest:
        qr_data = f"収穫日:{val_harvest}"
        qr_bytes = generate_qr(qr_data)
        st.image(qr_bytes, use_container_width=True)
        st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)

# --- 2列目: 出芽日 ---
with col2:
    st.subheader("出芽日")
    val_bud = st.text_input("日付を入力", value="8/23", key="bud")
    if val_bud:
        qr_data = f"出芽日:{val_bud}"
        qr_bytes = generate_qr(qr_data)
        st.image(qr_bytes, use_container_width=True)
        st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)

# --- 3列目: 開花日 ---
with col3:
    st.subheader("開花日")
    val_flower = st.text_input("日付を入力", value="8/24", key="flower")
    if val_flower:
        qr_data = f"開花日:{val_flower}"
        qr_bytes = generate_qr(qr_data)
        st.image(qr_bytes, use_container_width=True)
        st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)

# --- 4列目: 重さ ---
with col4:
    st.subheader("重さ")
    val_weight = st.text_input("重さを入力 (4桁)", value="0500", max_chars=4, key="weight")
    if val_weight:
        qr_data = f"重さ:{val_weight}"
        qr_bytes = generate_qr(qr_data)
        st.image(qr_bytes, use_container_width=True)
        st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)
