import streamlit as st
import pandas as pd
from pyzbar.pyzbar import decode
from PIL import Image
import datetime
from streamlit_gsheets import GSheetsConnection

# ページ設定
st.set_page_config(page_title="育成管理システム", layout="wide")

# --- Googleスプレッドシート接続 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("スプレッドシートへの接続設定が完了していません。Secretsの設定を確認してください。")
    st.stop()

def load_tags():
    # ttl=0 でキャッシュを無効化し、常に最新データを取得
    return conn.read(worksheet="Tags", ttl=0)

def load_items():
    return conn.read(worksheet="Items", ttl=0)

# --- データ操作関数 ---
def get_tag_info(tag_id):
    tags_df = load_tags()
    match = tags_df[tags_df['tag_id'] == tag_id]
    if not match.empty:
        code = match.iloc[0]['current_item_code']
        # 空白やNaNの場合は未割り当てと判定
        if pd.isna(code) or code == "":
            return None
        return str(code)
    return None

def get_item_info(item_code):
    items_df = load_items()
    match = items_df[items_df['item_code'] == item_code]
    if not match.empty:
        row = match.iloc[0]
        return {
            "sprout_date": row['sprout_date'] if pd.notna(row['sprout_date']) and row['sprout_date'] != "" else None,
            "bloom_date": row['bloom_date'] if pd.notna(row['bloom_date']) and row['bloom_date'] != "" else None,
            "weight": row['weight'] if pd.notna(row['weight']) and row['weight'] != "" else 0.0
        }
    return None

def register_new_item(tag_id):
    tags_df = load_tags()
    items_df = load_items()
    
    item_code = f"ITEM-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # 1. Tagsシートの更新
    if tag_id in tags_df['tag_id'].values:
        tags_df.loc[tags_df['tag_id'] == tag_id, 'current_item_code'] = item_code
    else:
        new_tag = pd.DataFrame({'tag_id': [tag_id], 'current_item_code': [item_code]})
        tags_df = pd.concat([tags_df, new_tag], ignore_index=True)
        
    # 2. Itemsシートの更新
    new_item = pd.DataFrame({
        'item_code': [item_code], 
        'sprout_date': [""], 
        'bloom_date': [""], 
        'weight': [0.0]
    })
    items_df = pd.concat([items_df, new_item], ignore_index=True)
    
    # スプレッドシートに書き込み
    conn.update(worksheet="Tags", data=tags_df)
    conn.update(worksheet="Items", data=items_df)
    
    return item_code

def update_item_info(item_code, sprout, bloom, weight):
    items_df = load_items()
    idx = items_df[items_df['item_code'] == item_code].index
    if not idx.empty:
        items_df.loc[idx, 'sprout_date'] = sprout if sprout else ""
        items_df.loc[idx, 'bloom_date'] = bloom if bloom else ""
        items_df.loc[idx, 'weight'] = weight
        conn.update(worksheet="Items", data=items_df)

def clear_tag_link(tag_id):
    tags_df = load_tags()
    idx = tags_df[tags_df['tag_id'] == tag_id].index
    if not idx.empty:
        tags_df.loc[idx, 'current_item_code'] = "" # 空文字列でリンク解除
        conn.update(worksheet="Tags", data=tags_df)

def parse_date(date_str):
    if date_str and pd.notna(date_str) and str(date_str).strip() != "":
        # スプレッドシートからの日付は文字列として処理
        return datetime.datetime.strptime(str(date_str), "%Y-%m-%d").date()
    return None

# --- UIレイアウト ---
if 'scanned_tag' not in st.session_state:
    st.session_state['scanned_tag'] = None

st.title("🌱 植物の育成管理システム (GSheets版)")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.header("1. QRコードの読み取り")
    st.write("使い回す物理タグ（QRコード）をスキャンしてください。")
    
    tab1, tab2 = st.tabs(["📷 カメラ", "⌨️ 手入力(テスト用)"])
    
    with tab1:
        camera_img = st.camera_input("QRコードを撮影", label_visibility="collapsed")
        if camera_img:
            img = Image.open(camera_img)
            decoded_objects = decode(img)
            
            if decoded_objects:
                for obj in decoded_objects:
                    tag_id = obj.data.decode('utf-8')
                    st.session_state['scanned_tag'] = tag_id
                    st.success(f"スキャン成功: {tag_id}")
                    st.rerun()
            else:
                st.warning("QRコードが検出できませんでした。")
                
    with tab2:
        with st.form("manual_form"):
            manual_tag = st.text_input("QRコードのテキスト (例: TAG-001)")
            if st.form_submit_button("読み込む") and manual_tag:
                st.session_state['scanned_tag'] = manual_tag.strip()
                st.rerun()

with col2:
    st.header("2. 個体の管理・記録")
    
    if st.session_state['scanned_tag']:
        tag_id = st.session_state['scanned_tag']
        st.markdown(f"**現在のスキャンタグ:** `{tag_id}`")
        
        # スプレッドシートから状態を確認
        with st.spinner('データベースと通信中...'):
            item_code = get_tag_info(tag_id)
        
        if not item_code:
            st.info("ℹ️ このQRコードはリンクが消去されています（未割り当て）。")
            st.write("このタグを使って新しい個体の記録を開始しますか？")
            if st.button("🌱 新しい商品番号を取得して登録", type="primary"):
                with st.spinner('スプレッドシートに書き込み中...'):
                    new_code = register_new_item(tag_id)
                st.success(f"新しい商品番号を割り当てました！ (番号: {new_code})")
                st.rerun()
                
        else:
            with st.spinner('データ取得中...'):
                item_data = get_item_info(item_code)
                
            if item_data:
                st.success(f"🌿 育成中の商品番号: **{item_code}**")
                
                with st.form("update_form"):
                    sprout_val = parse_date(item_data['sprout_date'])
                    bloom_val = parse_date(item_data['bloom_date'])
                    weight_val = item_data['weight'] if item_data['weight'] else 0.0
                    
                    new_sprout = st.date_input("出芽の日", value=sprout_val, format="YYYY/MM/DD")
                    new_bloom = st.date_input("開花の日", value=bloom_val, format="YYYY/MM/DD")
                    new_weight = st.number_input("重さ (g)", value=float(weight_val), step=1.0)
                    
                    if st.form_submit_button("💾 記録を保存・更新する"):
                        sprout_str = new_sprout.strftime("%Y-%m-%d") if new_sprout else ""
                        bloom_str = new_bloom.strftime("%Y-%m-%d") if new_bloom else ""
                        with st.spinner('スプレッドシートに書き込み中...'):
                            update_item_info(item_code, sprout_str, bloom_str, new_weight)
                        st.success("記録を更新しました！")
                        
                st.markdown("---")
                st.write("収穫などが完了し、このQRコードを使い回す場合はリンクを消去してください。")
                if st.button("🔗 QRコードのリンクを消去する", type="primary"):
                    with st.spinner('リンクを解除中...'):
                        clear_tag_link(tag_id)
                    st.session_state['scanned_tag'] = tag_id 
                    st.rerun()
            else:
                st.error("データが破損しています。")
    else:
        st.info("👈 左側のパネルからQRコードをスキャンしてください。")
