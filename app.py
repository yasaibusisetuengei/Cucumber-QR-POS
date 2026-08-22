import streamlit as st
import sqlite3
import pandas as pd
from pyzbar.pyzbar import decode
from PIL import Image
import datetime

# --- データベース設定 ---
DB_NAME = 'farm_management.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # QRコード(物理タグ)の状態を管理するテーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,
            current_item_code TEXT
        )
    ''')
    # 植物個体の成長記録を保存するテーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            item_code TEXT PRIMARY KEY,
            sprout_date TEXT,
            bloom_date TEXT,
            weight REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- データベース操作関数 ---
def get_tag_info(tag_id):
    """タグに紐づいている現在の個体番号を取得"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT current_item_code FROM tags WHERE tag_id = ?', (tag_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_item_info(item_code):
    """個体の記録を取得"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT sprout_date, bloom_date, weight FROM items WHERE item_code = ?', (item_code,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"sprout_date": row[0], "bloom_date": row[1], "weight": row[2]}
    return None

def register_new_item(tag_id):
    """新しい個体番号を発番し、タグと紐付ける"""
    # タイムスタンプを使って一意の商品番号（個体番号）を自動生成
    item_code = f"ITEM-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # タグがDBになければ登録
    c.execute('INSERT OR IGNORE INTO tags (tag_id) VALUES (?)', (tag_id,))
    # タグに新しい商品番号を紐付け
    c.execute('UPDATE tags SET current_item_code = ? WHERE tag_id = ?', (item_code, tag_id))
    # 個体テーブルに新規レコード作成
    c.execute('INSERT INTO items (item_code) VALUES (?)', (item_code,))
    
    conn.commit()
    conn.close()
    return item_code

def update_item_info(item_code, sprout, bloom, weight):
    """個体の記録を更新"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE items SET sprout_date=?, bloom_date=?, weight=? WHERE item_code=?', 
              (sprout, bloom, weight, item_code))
    conn.commit()
    conn.close()

def clear_tag_link(tag_id):
    """タグの紐付けを解除（初期化）"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE tags SET current_item_code = NULL WHERE tag_id = ?', (tag_id,))
    conn.commit()
    conn.close()

def parse_date(date_str):
    """DBの日付文字列をdatetime.dateオブジェクトに変換"""
    if date_str:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    return None

# --- UIレイアウト ---

st.set_page_config(page_title="育成管理システム", layout="wide")

if 'scanned_tag' not in st.session_state:
    st.session_state['scanned_tag'] = None

st.title("🌱 植物の育成管理システム")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.header("1. QRコードの読み取り")
    st.write("使い回す物理タグ（QRコード）をスキャンしてください。")
    
    # タブで入力方法を切り替え（テスト用に手入力も残しています）
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
                    st.rerun() # スキャン完了後、右側の画面を更新
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
        
        # データベースからタグの状態を確認
        item_code = get_tag_info(tag_id)
        
        if not item_code:
            # --- リンク消去済み（未割り当て）の場合 ---
            st.info("ℹ️ このQRコードはリンクが消去されています（未割り当て）。")
            st.write("このタグを使って新しい個体の記録を開始しますか？")
            
            if st.button("🌱 新しい商品番号を取得して登録", type="primary"):
                new_code = register_new_item(tag_id)
                st.success(f"新しい商品番号を割り当てました！ (番号: {new_code})")
                st.rerun()
                
        else:
            # --- 育成中（割り当て済み）の場合 ---
            item_data = get_item_info(item_code)
            st.success(f"🌿 育成中の商品番号: **{item_code}**")
            
            with st.form("update_form"):
                # DBの値が存在しない場合はNoneをセット（未設定状態にする）
                sprout_val = parse_date(item_data['sprout_date'])
                bloom_val = parse_date(item_data['bloom_date'])
                weight_val = item_data['weight'] if item_data['weight'] else 0.0
                
                # Streamlitのdate_inputはvalue=Noneで未入力を表現可能
                new_sprout = st.date_input("出芽の日", value=sprout_val, format="YYYY/MM/DD")
                new_bloom = st.date_input("開花の日", value=bloom_val, format="YYYY/MM/DD")
                new_weight = st.number_input("重さ (g)", value=float(weight_val), step=1.0)
                
                if st.form_submit_button("💾 記録を保存・更新する"):
                    sprout_str = new_sprout.strftime("%Y-%m-%d") if new_sprout else None
                    bloom_str = new_bloom.strftime("%Y-%m-%d") if new_bloom else None
                    update_item_info(item_code, sprout_str, bloom_str, new_weight)
                    st.success("記録を更新しました！")
                    
            st.markdown("---")
            st.write("収穫などが完了し、このQRコードを別の植物に使い回す場合はリンクを消去してください。")
            st.write("※リンクを消去しても、これまでの育成記録はデータベースに保存されています。")
            
            if st.button("🔗 QRコードのリンクを消去する", type="primary"):
                clear_tag_link(tag_id)
                st.session_state['scanned_tag'] = tag_id # 画面を未割り当て状態に移行させる
                st.rerun()
                
    else:
        st.info("👈 左側のパネルからQRコードをスキャンしてください。")
