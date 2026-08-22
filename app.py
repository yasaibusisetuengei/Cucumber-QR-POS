import streamlit as st
import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ページ全体のレイアウトをワイド（画面横幅いっぱい）に設定
st.set_page_config(page_title="農作業記録QRコード生成アプリ", layout="wide")

st.title("農作業記録QRコード生成")

def generate_qr_with_text(text):
    if not text:
        return None

    # 1. QRコードの生成
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 中央に文字を入れるため誤り訂正レベルを「H(高)」に設定
        box_size=12,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    
    # PIL画像に変換 (RGBモード)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    
    # 2. 中央にテキストを描画する処理
    draw = ImageDraw.Draw(qr_img)
    img_w, img_h = qr_img.size
    
    # フォントの設定（環境に応じてデフォルトフォントを利用）
    try:
        # 文字サイズを調整（QRコードの大きさに応じて適宜変更）
        font_size = int(img_w * 0.16)
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    # テキストの描画サイズを取得
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # 文字の表示位置（中央）
    x = (img_w - text_w) / 2
    y = (img_h - text_h) / 2

    # 文字背景の白い矩形（読取精度を保ちつつ読みやすくするための余白）
    padding = 8
    rect_x0 = x - padding
    rect_y0 = y - padding
    rect_x1 = x + text_w + padding
    rect_y1 = y + text_h + padding

    # 白色の背景枠を描画
    draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill="white", outline="black", width=2)

    # 黒色で中央にテキストを描画
    draw.text((x, y), text, fill="black", font=font)

    # 3. Streamlit表示用にバイトストリームへ変換
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    return buf.getvalue()

# 画面を4つのカラムに分割
col1, col2, col3, col4 = st.columns(4)

# --- 1列目: 収穫日 ---
with col1:
    st.subheader("収穫日")
    date_harvest = st.text_input("収穫日を入力", value="8/22", key="harvest")
    if date_harvest:
        qr_bytes = generate_qr_with_text(date_harvest)
        st.image(qr_bytes, caption=f"収穫日: {date_harvest}", use_container_width=True)

# --- 2列目: 出芽日 ---
with col2:
    st.subheader("出芽日")
    date_bud = st.text_input("出芽日を入力", value="8/23", key="bud")
    if date_bud:
        qr_bytes = generate_qr_with_text(date_bud)
        st.image(qr_bytes, caption=f"出芽日: {date_bud}", use_container_width=True)

# --- 3列目: 開花日 ---
with col3:
    st.subheader("開花日")
    date_flower = st.text_input("開花日を入力", value="8/24", key="flower")
    if date_flower:
        qr_bytes = generate_qr_with_text(date_flower)
        st.image(qr_bytes, caption=f"開花日: {date_flower}", use_container_width=True)

# --- 4列目: 重さ ---
with col4:
    st.subheader("重さ")
    weight = st.text_input("重さを入力 (4桁)", value="0500", max_chars=4, key="weight")
    if weight:
        qr_bytes = generate_qr_with_text(weight)
        st.image(qr_bytes, caption=f"重さ: {weight}g", use_container_width=True)
