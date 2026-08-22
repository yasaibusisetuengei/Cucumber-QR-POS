import streamlit as st
import qrcode
from io import BytesIO

# ページ設定
st.set_page_config(page_title="QRコード生成", layout="wide")

# スタイル調整（余白を最小化し、1画面に収めるCSS）
st.markdown("""
    <style>
    /* 全体の上下余白（パディング）を小さく削減 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    /* ヘッダー/フッター等の不要なスペースを非表示 */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    /* タイトルの文字サイズと下余白を詰める */
    h1 {
        font-size: 1.2rem !important;
        margin-bottom: 0.3rem !important;
        padding-top: 0rem !important;
    }
    
    /* 入力欄の余白とラベルサイズを詰める */
    .stTextInput > label {
        font-size: 0.85rem !important;
        font-weight: bold !important;
        margin-bottom: -0.2rem !important;
    }
    .stTextInput > div > div > input {
        height: 2rem !important;
        font-size: 0.9rem !important;
    }
    
    /* QRコード下のラベル表示 */
    .qr-label {
        font-size: 1rem !important;
        font-weight: bold !important;
        text-align: center;
        color: #ffffff;
        margin-top: 2px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("農作業記録QRコード生成")

# QRコード生成関数（表示幅に合わせて画像解像度も少し小さく最適化）
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

# 各カラムの定義
items = [
    (col1, "収穫日", "8/22", "harvest"),
    (col2, "出芽日", "8/23", "bud"),
    (col3, "開花日", "8/24", "flower"),
    (col4, "重さ", "0500", "weight")
]

for col, label, default_val, key in items:
    with col:
        # 重さの場合は4桁制限のアドバイス
        max_c = 4 if key == "weight" else None
        val = st.text_input(label, value=default_val, key=key, max_chars=max_c)
        if val:
            qr_data = f"{label}:{val}"
            qr_bytes = generate_qr(qr_data)
            # 画像を表示
            st.image(qr_bytes, use_container_width=True)
            # QRコード下のテキストを表示
            st.markdown(f'<div class="qr-label">{qr_data}</div>', unsafe_allow_html=True)
