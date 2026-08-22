import streamlit as st
import qrcode
from io import BytesIO

# ページ設定
st.set_page_config(page_title="QRコード生成", layout="wide")

# スタイル調整（余白削減およびQRコード中央揃え用CSS）
st.markdown("""
    <style>
    /* 全体の上下左右余白を削減 */
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    /* 不要な標準ヘッダー類を非表示 */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    /* タイトルとスライダーの余白調整 */
    h1 {
        font-size: 1.1rem !important;
        margin-bottom: 0.2rem !important;
    }
    
    /* 入力欄の見た目を調整 */
    .stTextInput > label {
        font-size: 0.85rem !important;
        font-weight: bold !important;
        margin-bottom: -0.2rem !important;
    }
    .stTextInput > div > div > input {
        height: 1.8rem !important;
        font-size: 0.85rem !important;
    }
    
    /* QRコードとラベルをカラム内で中央配置 */
    [data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    [data-testid="stColumn"] > div {
        width: 100%;
    }
    
    /* QRコード下のラベルテキスト */
    .qr-label {
        font-size: 0.9rem !important;
        font-weight: bold !important;
        text-align: center;
        color: #ffffff;
        margin-top: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# ヘッダーとサイズ調整スライダーの配置
top_col1, top_col2 = st.columns([2, 3])

with top_col1:
    st.title("農作業記録QRコード生成")

with top_col2:
    # QRコードの表示幅（幅50px〜250px）を調節するスライダー
    qr_width = st.slider("QRコードの表示サイズ (px)", min_value=50, max_value=250, value=110, step=5)

# QRコード生成関数
def generate_qr(text):
    if not text:
        return None
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# 4列レイアウト
col1, col2, col3, col4 = st.columns(4)

items = [
    (col1, "収穫日", "8/22", "harvest"),
    (col2, "出芽日", "8/23", "bud"),
    (col3, "開花日", "8/24", "flower"),
    (col4, "重さ", "0500", "weight")
]

for col, label, default_val, key in items:
    with col:
        max_c = 4 if key == "weight" else None
        val = st.text_input(label, value=default_val, key=key, max_chars=max_c)
        if val:
            qr_data = f"{label}:{val}"
            qr_bytes = generate_qr(qr_data)
            
            # スライダーで設定した幅(width)を適用して表示
            st.image(qr_bytes, width=qr_width)
            st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)
