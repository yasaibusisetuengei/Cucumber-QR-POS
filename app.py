import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import cv2
import numpy as np
import urllib.request
import time
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
import streamlit.components.v1 as components

# ==========================================
# 🌟 データベース接続と設定の初期化
# ==========================================
st.set_page_config(page_title="管理＆判定システム", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# 保存用フォルダの作成
SAVE_DIR = "saved_images"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def load_settings():
    for attempt in range(3):
        try:
            df = conn.read(worksheet="Settings", ttl=0, dtype=str)
            if df is None or df.empty:
                raise ValueError("Settings empty")
            return dict(zip(df['key'], df['value']))
        except Exception:
            if attempt < 2:
                time.sleep(2)
            else:
                default_settings = {
                    "crop_name": "キュウリ",
                    "emoji": "🥒",
                    "date_count": "3",
                    "date_labels": "発芽日,開花日,収穫日",
                    "area_options": "1,2,3,4,5,6,7,8,9,10,11,12"
                }
                try:
                    df = pd.DataFrame(list(default_settings.items()), columns=["key", "value"])
                    conn.update(worksheet="Settings", data=df)
                except Exception:
                    pass
                return default_settings

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

if "grade_result" not in st.session_state:
    st.session_state.grade_result = None
if "processed_qrs" not in st.session_state:
    st.session_state.processed_qrs = set()
if "last_scanned_tag" not in st.session_state:
    st.session_state.last_scanned_tag = None

def clear_grade_result():
    st.session_state.grade_result = None

c_name = st.session_state.settings.get("crop_name", "キュウリ")
c_emoji = st.session_state.settings.get("emoji", "🥒")

# ==========================================
# 🌟 条件②: 通知音・振動機能 (カメラ撮影時も必ず再生)
# ==========================================
def play_notification_sound():
    js_code = """
    <script>
    try {
        if (navigator.vibrate) { navigator.vibrate([100, 50, 100]); }
        var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        var oscillator = audioCtx.createOscillator();
        var gainNode = audioCtx.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioCtx.currentTime);
        gainNode.gain.setValueAtTime(0.2, audioCtx.currentTime);
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.start();
        setTimeout(function(){ oscillator.stop(); }, 200);
    } catch(e) { console.log("Audio/Vibration error:", e); }
    </script>
    """
    components.html(js_code, height=0, width=0)

# ==========================================
# 🌟 条件③: スマホローカル（端末）への画像自動保存ヘルパー
# ==========================================
def save_image_to_device_and_server(image_bytes, prefix="capture"):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.jpg"
    
    # 1. サーバー側に保存
    server_path = os.path.join(SAVE_DIR, filename)
    with open(server_path, "wb") as f:
        f.write(image_bytes)
        
    # 2. スマホ端末（ブラウザダウンロード）へ自動ダウンロード保存させるJavaScript
    b64_str = base64.b64encode(image_bytes).decode('utf-8')
    download_js = f"""
    <script>
    var a = document.createElement('a');
    a.href = 'data:image/jpeg;base64,{b64_str}';
    a.download = '{filename}';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    </script>
    """
    components.html(download_js, height=0, width=0)
    return server_path

# ==========================================
# 🌟 GitHub サンプル画像のURL設定
# ==========================================
SAMPLE1_URL = "https://raw.githubusercontent.com//yasaibusisetusengei/Cucumber-QR-POS/main/sample/sample1.png"
SAMPLE2_URL = "https://raw.githubusercontent.com//yasaibusisetusengei/Cucumber-QR-POS/main/sample/sample2.jpg"

def get_image_bytes_from_url(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        st.error(f"サンプル画像の読み込みに失敗しました: {e}")
        return None

# ==========================================
# 1. 階級判定用の定数設定
# ==========================================
A4_W_MM, A4_H_MM = 297.0, 210.0
PPM = 3.0
A4_W_PX, A4_H_PX = int(A4_W_MM * PPM), int(A4_H_MM * PPM)
MARKER_OFFSET_MM = 15.0
OFFSET_PX = int(MARKER_OFFSET_MM * PPM)
DIST_5CM_PX = 50.0 * PPM

COLOR_CONTOUR = (0, 255, 0)
COLOR_TABLE_LINE = (255, 255, 0)
COLOR_CURVE_LINE = (255, 0, 0)
COLOR_THICKNESS = (255, 0, 255)

# ==========================================
# 2. データベース操作関数
# ==========================================
def load_tags():
    for attempt in range(3):
        try:
            df = conn.read(worksheet="Tags", ttl=600, dtype=str)
            return df.fillna("")
        except Exception:
            if attempt < 2: time.sleep(2)
            else: st.stop()

def load_items():
    for attempt in range(3):
        try:
            df = conn.read(worksheet="Items", ttl=600, dtype=str)
            for col in ['weight', 'length', 'thickness', 'curve']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            for col in df.columns:
                if col not in ['weight', 'length', 'thickness', 'curve']:
                    df[col] = df[col].fillna("")
            return df
        except Exception:
            if attempt < 2: time.sleep(2)
            else: st.stop()

def get_tag_info(tag_id):
    tags_df = load_tags()
    if tags_df is None or tags_df.empty: return None
    tags_df['tag_id'] = tags_df['tag_id'].astype(str)
    match = tags_df[tags_df['tag_id'] == str(tag_id)]
    if not match.empty:
        code = match.iloc[0]['current_item_code']
        if code != "": return str(code)
    return None

def register_new_item(tag_id):
    tags_df = load_tags()
    items_df = load_items()
    
    if tags_df is None: tags_df = pd.DataFrame(columns=['tag_id', 'current_item_code'])
    if items_df is None: items_df = pd.DataFrame()
    
    tags_df['tag_id'] = tags_df['tag_id'].astype(str)
    item_code = f"ITEM-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    if str(tag_id) in tags_df['tag_id'].values:
        tags_df.loc[tags_df['tag_id'] == str(tag_id), 'current_item_code'] = item_code
    else:
        new_tag = pd.DataFrame({'tag_id': [str(tag_id)], 'current_item_code': [item_code]})
        tags_df = pd.concat([tags_df, new_tag], ignore_index=True)
        
    new_item = {
        'item_code': [item_code], 'weight': [0.0],
        'area_number': ["1"], 'comment': [""], 'grade': [""], 
        'length': [0.0], 'thickness': [0.0], 'curve': [0.0],
        'record_image': [""], 'grade_image': [""]
    }
    date_count = int(st.session_state.settings.get("date_count", 3))
    for i in range(1, date_count + 1):
        new_item[f'date_{i}'] = [""]
        
    new_item_df = pd.DataFrame(new_item)
    items_df = pd.concat([items_df, new_item_df], ignore_index=True)
    
    conn.update(worksheet="Tags", data=tags_df)
    conn.update(worksheet="Items", data=items_df)
    st.cache_data.clear()
    return item_code

def update_item_record(item_code, **kwargs):
    items_df = load_items()
    items_df['item_code'] = items_df['item_code'].astype(str)
    idx = items_df[items_df['item_code'] == str(item_code)].index
    
    if not idx.empty:
        for key, val in kwargs.items():
            if key not in items_df.columns:
                items_df[key] = ""
            items_df[key] = items_df[key].astype(object)
            items_df.loc[idx, key] = val
            
        conn.update(worksheet="Items", data=items_df)
        st.cache_data.clear()

def unbind_tag(tag_id):
    tags_df = load_tags()
    tags_df['tag_id'] = tags_df['tag_id'].astype(str)
    idx = tags_df[tags_df['tag_id'] == str(tag_id)].index
    if not idx.empty:
        tags_df.loc[idx, 'current_item_code'] = ""
        conn.update(worksheet="Tags", data=tags_df)
        st.cache_data.clear()
        return True
    return False

def read_qr_from_bytes(file_bytes):
    img = cv2.imdecode(file_bytes, 1)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return str(data).strip() if data else None

# ==========================================
# 3. OpenCV 画像処理・計測関数
# ==========================================
def detect_and_warp(image: np.ndarray):
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, _ = detector.detectMarkers(image)
    if ids is None or len(ids) < 4:
        image = cv2.flip(image, 1)
        corners, ids, _ = detector.detectMarkers(image)
    if ids is None or len(ids) < 4:
        return None, "マーカーを探しています...（A4ボードの四隅を写してください）"
    centers = np.array([corner[0].mean(axis=0) for corner in corners])
    sorted_x = centers[np.argsort(centers[:, 0])]
    left_pts, right_pts = sorted_x[:2], sorted_x[2:]
    tl, bl = left_pts[np.argsort(left_pts[:, 1])]
    tr, br = right_pts[np.argsort(right_pts[:, 1])]
    src_pts = np.array([tl, tr, br, bl], dtype=np.float32)
    dst_pts = np.array([
        [OFFSET_PX, OFFSET_PX], [A4_W_PX - OFFSET_PX, OFFSET_PX],
        [A4_W_PX - OFFSET_PX, A4_H_PX - OFFSET_PX], [OFFSET_PX, A4_H_PX - OFFSET_PX]
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(image, M, (A4_W_PX, A4_H_PX))
    return warped, None

def extract_cucumber_contour(warped_img: np.ndarray):
    hsv = cv2.cvtColor(warped_img, cv2.COLOR_RGB2HSV)
    lower_green, upper_green = np.array([35, 40, 40]), np.array([85, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return None, f"{c_name}が検出できません。"
    return max(contours, key=cv2.contourArea), None

def calculate_length(contour):
    approx = cv2.approxPolyDP(contour, 0.01 * cv2.arcLength(contour, True), True)
    max_dist = 0.0
    end1, end2 = None, None
    for i in range(len(approx)):
        for j in range(i + 1, len(approx)):
            d = np.linalg.norm(approx[i][0] - approx[j][0])
            if d > max_dist:
                max_dist, end1, end2 = d, approx[i][0], approx[j][0]
    return (max_dist / PPM) / 10.0, end1, end2

def calculate_curve(contour):
    hull = cv2.convexHull(contour, returnPoints=False)
    defects = cv2.convexityDefects(contour, hull)
    curve_px, curve_point, defect_start, defect_end, foot = 0.0, None, None, None, None
    if defects is not None:
        max_depth = 0
        best_defect = None
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i].flatten()
            if d > max_depth:
                max_depth, best_defect = d, defects[i].flatten()
        if best_defect is not None:
            s, e, f, d = best_defect
            defect_start, defect_end = contour[s][0], contour[e][0]
            curve_point = contour[f][0]
            curve_px = d / 256.0
            v_line = defect_end.astype(np.float32) - defect_start.astype(np.float32)
            v_far = curve_point.astype(np.float32) - defect_start.astype(np.float32)
            l2 = np.dot(v_line, v_line)
            if l2 == 0: foot = defect_start.astype(np.float32)
            else: foot = defect_start.astype(np.float32) + max(0.0, min(1.0, np.dot(v_far, v_line) / l2)) * v_line
    return (curve_px / PPM) / 10.0, defect_start, defect_end, curve_point, foot

def calculate_thickness(start_pt, end_pt, dist_px, contour):
    dists = np.linalg.norm(contour[:, 0, :] - start_pt, axis=1)
    idx_start = np.argmin(dists)
    n = len(contour)
    def find_intersection(step):
        prev_pt, prev_d = contour[idx_start][0].astype(float), dists[idx_start]
        for i in range(1, n // 2):
            idx = (idx_start + i * step) % n
            pt, d = contour[idx][0].astype(float), dists[idx]
            if d >= dist_px:
                if d == prev_d: return pt
                return prev_pt + ((dist_px - prev_d) / (d - prev_d)) * (pt - prev_pt)
            prev_pt, prev_d = pt, d
        return None
    p1, p2 = find_intersection(1), find_intersection(-1)
    if p1 is not None and p2 is not None: return (np.linalg.norm(p1 - p2) / PPM) / 10.0, p1, p2
    return 0.0, None, None

def evaluate_grade(length_cm, curve_cm, head_thick_cm, tail_thick_cm):
    grade = "規格外"
    curve_grade = "A" if curve_cm <= 1.5 else "B" if curve_cm <= 3.0 else "C" if curve_cm <= 5.0 else "規格外"
    if curve_grade != "規格外" and (1.0 <= head_thick_cm <= 3.0) and (1.0 <= tail_thick_cm <= 3.0): grade = curve_grade
    size_mark = ""
    if grade == "A": size_mark = "L" if 22<=length_cm<=26 else "M" if 18<=length_cm<22 else "S" if 16<=length_cm<18 else ""
    elif grade == "B": size_mark = "2L" if 28<=length_cm<=29 else "L" if 23<=length_cm<28 else "M" if 18<=length_cm<23 else "S" if 16<=length_cm<18 else ""
    elif grade == "C": size_mark = "L" if 23<=length_cm<=29 else "M" if 16<=length_cm<23 else ""
    return grade, f"{grade}{size_mark}" if grade != "規格外" else "規格外"

def draw_results(warped, contour, ds, de, cp, foot, hp1, hp2, tp1, tp2):
    res = warped.copy()
    cv2.drawContours(res, [contour], -1, COLOR_CONTOUR, 2)
    if ds is not None and de is not None: cv2.line(res, tuple(ds.astype(int)), tuple(de.astype(int)), COLOR_TABLE_LINE, 2)
    if foot is not None and cp is not None:
        cv2.line(res, tuple(foot.astype(int)), tuple(cp.astype(int)), COLOR_CURVE_LINE, 3)
        cv2.circle(res, tuple(cp.astype(int)), 6, COLOR_CURVE_LINE, -1)
    if hp1 is not None and hp2 is not None: cv2.line(res, tuple(hp1.astype(int)), tuple(hp2.astype(int)), COLOR_THICKNESS, 3)
    if tp1 is not None and tp2 is not None: cv2.line(res, tuple(tp1.astype(int)), tuple(tp2.astype(int)), COLOR_THICKNESS, 3)
    return res

def process_measurement(image):
    if image is None: return None, "画像がありません", None, None, None, None, None
    warped, err = detect_and_warp(image)
    if err: return image, f"<h3 style='color:red;'>{err}</h3>", None, None, None, None, None
    contour, err = extract_cucumber_contour(warped)
    if err: return warped, f"<h3 style='color:red;'>{err}</h3>", None, None, None, None, None
    
    length_cm, end1, end2 = calculate_length(contour)
    curve_cm, ds, de, cp, foot = calculate_curve(contour)
    head_thick_cm, hp1, hp2 = calculate_thickness(end1, end2, DIST_5CM_PX, contour)
    tail_thick_cm, tp1, tp2 = calculate_thickness(end2, end1, DIST_5CM_PX, contour)
    avg_thick_cm = (head_thick_cm + tail_thick_cm) / 2.0 if head_thick_cm > 0 else 1.5

    grade, display_grade = evaluate_grade(length_cm, curve_cm, head_thick_cm, tail_thick_cm)
    rank_bg = {"A":"#e8f5e9", "B":"#fff3cd", "C":"#f8d7da"}.get(grade, "#f8f9fa")
    
    res_img = draw_results(warped, contour, ds, de, cp, foot, hp1, hp2, tp1, tp2)
    html = f"""
    <div style="background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; color: black;">
        <h3 style="text-align: center; margin-top: 0; color: #2e7d32;">📐 計測・判定結果</h3>
        <p>📏 <b>長さ:</b> {length_cm:.1f} cm</p>
        <p>⭕ <b>太さ:</b> {avg_thick_cm:.1f} cm</p>
        <p>〰️ <b>曲がり:</b> {curve_cm:.1f} cm</p>
        <div style="background-color: {rank_bg}; padding: 12px; text-align: center; font-size: 1.2em; border-radius: 8px; margin-top: 10px;">
            <b>階級: {display_grade}</b>
        </div>
    </div>
    """
    return res_img, html, length_cm, avg_thick_cm, curve_cm, display_grade, warped

# ==========================================
# 4. Streamlit UI 構成 (3つのタブ)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🌱 生育記録", f"{c_emoji} 収穫・階級判定", "⚙️ 初期設定"])

# --- タブ1: 生育記録 ---
with tab1:
    st.header("🌱 生育記録 (QRスキャン)")
    img_source_qr = st.radio("入力方法", ["カメラ", "アップロード", "サンプル画像 (sample1)"], key="qr_radio")
    
    file_bytes_qr = None
    if img_source_qr == "カメラ":
        qr_img = st.camera_input("QRコードを撮影", key="qr_camera")
        if qr_img:
            st.session_state.temp_record_bytes = qr_img.getvalue()
            file_bytes_qr = np.asarray(bytearray(st.session_state.temp_record_bytes), dtype=np.uint8)
            # ★条件③: スマホ端末＆サーバーに撮影画像を自動保存
            save_image_to_device_and_server(st.session_state.temp_record_bytes, prefix="record")
    elif img_source_qr == "アップロード":
        qr_img = st.file_uploader("QRコード画像を選択", type=["jpg", "jpeg", "png"], key="qr_upload")
        if qr_img: file_bytes_qr = np.asarray(bytearray(qr_img.read()), dtype=np.uint8)
    else:
        st.info("サンプル画像 (sample1.png) を使用します。")
        raw_data = get_image_bytes_from_url(SAMPLE1_URL)
        if raw_data: file_bytes_qr = np.asarray(bytearray(raw_data), dtype=np.uint8)

    if file_bytes_qr is not None:
        if img_source_qr in ["アップロード", "サンプル画像 (sample1)"]:
            cv_img_qr = cv2.imdecode(file_bytes_qr, 1)
            st.image(cv2.cvtColor(cv_img_qr, cv2.COLOR_BGR2RGB), use_container_width=True)
            
        tag_id = read_qr_from_bytes(file_bytes_qr)
        
        if tag_id:
            if st.session_state.last_scanned_tag != tag_id:
                # ★条件②: カメラ撮影時でも必ず音を鳴らす
                play_notification_sound()
                st.session_state.last_scanned_tag = tag_id
                
            st.success(f"🏷️ タグを認識しました: {tag_id}")
            item_code = get_tag_info(tag_id)
            if not item_code:
                item_code = register_new_item(tag_id)
                st.info("新しいアイテムとして登録しました。")
            
            items_df = load_items()
            match = items_df[items_df['item_code'] == item_code]
            item_data = match.iloc[0].to_dict() if not match.empty else {}
            
            def clean_date_str(val):
                s = str(val).strip()
                return "" if s == "nan" or s == "None" else s
            def parse_date(d_str):
                if d_str:
                    try: return pd.to_datetime(d_str).date()
                    except: pass
                return None

            date_count = int(st.session_state.settings.get("date_count", 3))
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            
            # --- 自動更新ロジック ---
            if tag_id not in st.session_state.processed_qrs:
                already_scanned = False
                for i in range(1, date_count + 1):
                    if clean_date_str(item_data.get(f'date_{i}', '')) == today_str:
                        already_scanned = True
                        break
                
                if already_scanned:
                    st.info("✅ 本日読み込み済みです。")
                else:
                    update_kwargs = {}
                    updated = False
                    for i in range(1, date_count + 1):
                        if not clean_date_str(item_data.get(f'date_{i}', '')):
                            update_kwargs[f'date_{i}'] = today_str
                            updated = True
                            break
                    
                    if updated:
                        update_item_record(item_code, **update_kwargs)
                        st.success("🌱 スキャンを検知し、自動でデータベースを更新しました！")
                        match = load_items().query(f"item_code == '{item_code}'")
                        item_data = match.iloc[0].to_dict() if not match.empty else {}
                st.session_state.processed_qrs.add(tag_id)

            st.write(f"📝 編集対象コード: `{item_code}`")
            
            # エリア番号の設定反映
            area_opts = [x.strip() for x in st.session_state.settings.get("area_options", "1").split(",") if x.strip()]
            current_area = clean_date_str(item_data.get('area_number', area_opts[0] if area_opts else "1"))
            if current_area not in area_opts: area_opts.insert(0, current_area)
            new_area = st.selectbox("試験エリア番号", area_opts, index=area_opts.index(current_area))
            
            # 動的日付項目の配置
            date_labels = st.session_state.settings.get("date_labels", "").split(",")
            cols = st.columns(3)
            for i in range(date_count):
                lbl = date_labels[i] if i < len(date_labels) else f"日付{i+1}"
                d_val_str = clean_date_str(item_data.get(f'date_{i+1}', ''))
                if f"d{i+1}_{item_code}" not in st.session_state:
                    st.session_state[f"d{i+1}_{item_code}"] = parse_date(d_val_str)
                
                with cols[i % 3]:
                    st.session_state[f"d{i+1}_{item_code}"] = st.date_input(lbl, value=st.session_state[f"d{i+1}_{item_code}"], key=f"date_input_{i}_{item_code}")
                    if st.button(f"🗑️ {lbl}を消去", key=f"clear_d{i+1}_{item_code}"):
                        st.session_state[f"d{i+1}_{item_code}"] = None
                        widget_key = f"date_input_{i}_{item_code}"
                        if widget_key in st.session_state:
                            del st.session_state[widget_key]
                        st.rerun()
            
            new_comment = st.text_area("コメント（自由入力）", value=clean_date_str(item_data.get('comment', '')))
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("💾 記録をまとめて更新する", type="primary", use_container_width=True):
                update_kwargs = {'area_number': str(new_area), 'comment': str(new_comment)}
                for i in range(date_count):
                    val = st.session_state[f"d{i+1}_{item_code}"]
                    update_kwargs[f"date_{i+1}"] = val.strftime("%Y-%m-%d") if val else ""
                
                update_item_record(item_code, **update_kwargs)
                st.success(f"✅ アイテム【{item_code}】の記録を更新しました！")
                
        else:
            st.error("QRコードを検出できませんでした。再撮影してください。")

# --- タブ2: 収穫・階級判定 ---
with tab2:
    st.header(f"{c_emoji} 収穫・階級判定 ({c_name})")
    col1, col2 = st.columns(2)
    with col1:
        img_source_grade = st.radio("画像入力", ["カメラ", "アップロード", "サンプル画像 (sample2)"], key="grade_radio", on_change=clear_grade_result)
        file_bytes_grade = None
        if img_source_grade == "カメラ":
            c_img = st.camera_input(f"{c_name}を撮影（A4マーカー枠＆QRコード必須）", key="grade_camera", on_change=clear_grade_result)
            if c_img:
                st.session_state.temp_grade_bytes = c_img.getvalue()
                file_bytes_grade = np.asarray(bytearray(st.session_state.temp_grade_bytes), dtype=np.uint8)
                # ★条件③: スマホ端末＆サーバーに撮影画像を自動保存
                save_image_to_device_and_server(st.session_state.temp_grade_bytes, prefix="grade")
        elif img_source_grade == "アップロード":
            c_img = st.file_uploader("画像を選択", type=["jpg", "jpeg", "png"], key="grade_upload", on_change=clear_grade_result)
            if c_img: file_bytes_grade = np.asarray(bytearray(c_img.read()), dtype=np.uint8)
        else:
            st.info("サンプル画像 (sample2.jpg) を使用します。")
            raw_data = get_image_bytes_from_url(SAMPLE2_URL)
            if raw_data: file_bytes_grade = np.asarray(bytearray(raw_data), dtype=np.uint8)

        if file_bytes_grade is not None and img_source_grade in ["アップロード", "サンプル画像 (sample2)"]:
            cv_img_grade_preview = cv2.imdecode(file_bytes_grade, 1)
            st.image(cv2.cvtColor(cv_img_grade_preview, cv2.COLOR_BGR2RGB), use_container_width=True)

        grade_btn = st.button("📏 計測して階級を判定", type="primary")

    with col2:
        if grade_btn and file_bytes_grade is not None:
            cv_img = cv2.imdecode(file_bytes_grade, 1)
            cv_img_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            res_img, html, l_cm, t_cm, c_cm, grade_str, warped = process_measurement(cv_img_rgb)
            
            tag_id = None
            if l_cm is not None:
                tag_id = read_qr_from_bytes(file_bytes_grade)
                if not tag_id and warped is not None:
                    detector = cv2.QRCodeDetector()
                    warped_bgr = cv2.cvtColor(warped, cv2.RGB2BGR)
                    data, _, _ = detector.detectAndDecode(warped_bgr)
                    tag_id = str(data).strip() if data else None
            
            st.session_state.grade_result = {
                'res_img': res_img, 'html': html, 'l_cm': l_cm, 't_cm': t_cm,
                'c_cm': c_cm, 'grade_str': grade_str, 'tag_id': tag_id
            }

        if st.session_state.grade_result is not None:
            res = st.session_state.grade_result
            if res['res_img'] is not None: st.image(res['res_img'], channels="RGB")
            if res['html']: st.markdown(res['html'], unsafe_allow_html=True)
            
            if res['l_cm'] is not None:
                if res['tag_id']:
                    if st.session_state.last_scanned_tag != res['tag_id']:
                        # ★条件②: カメラ撮影時でも必ず音を鳴らす
                        play_notification_sound()
                        st.session_state.last_scanned_tag = res['tag_id']
                        
                    st.success(f"✅ タグ【{res['tag_id']}】を検出しました。重さを入力して登録を完了させてください。")
                    with st.form("register_grade_form"):
                        harvest_weight = st.number_input("重さ (g)", min_value=0.0, step=1.0, value=100.0, key="harvest_weight")
                        submit_btn = st.form_submit_button("💾 データベースに登録", type="primary")
                        
                        if submit_btn:
                            item_code = get_tag_info(res['tag_id'])
                            if not item_code: item_code = register_new_item(res['tag_id'])
                            
                            update_kwargs = {
                                'length': float(res['l_cm']), 'thickness': float(res['t_cm']),
                                'curve': float(res['c_cm']), 'grade': str(res['grade_str']),
                                'weight': float(harvest_weight)
                            }
                            
                            update_item_record(item_code, **update_kwargs)
                            st.success(f"🎉 アイテム【{item_code}】の情報を登録しました！")
                else:
                    st.error("⚠️ 画像からQRコードを検出できませんでした。計測は完了しましたが、データベースには登録できません。")

    st.divider()
    with st.expander("🔗 QRコードの使いまわし（タグのリンク解除）"):
        st.write(f"QRコードを再利用して新しい{c_name}に使用する場合、現在のアイテムとの紐づけを解除します。")
        unbind_target_tag = st.text_input("リンク解除するQRタグ番号", key="unbind_tag_input")
        if st.button("🔓 リンク解除を実行", type="secondary"):
            if unbind_target_tag:
                if unbind_tag(unbind_target_tag):
                    st.success(f"タグ【{unbind_target_tag}】のリンクを解除しました！")
                else:
                    st.warning(f"タグが見つからないか、すでに解除されています。")
            else:
                st.error("タグ番号を入力してください。")

# --- タブ3: 初期設定 (カスタマイズ・QR生成) ---
with tab3:
    st.header("⚙️ システム初期設定")
    st.write("設定した内容はスプレッドシート(Settingsシート)に記録され、起動時に反映されます。")
    
    with st.form("settings_form"):
        new_crop = st.text_input("作物名", value=st.session_state.settings.get("crop_name", "キュウリ"))
        new_emoji = st.text_input("絵文字アイコン", value=st.session_state.settings.get("emoji", "🥒"))
        st.divider()
        st.write("📅 生育記録の項目名設定")
        date_count = st.number_input("測定したい日付の数 (最大10)", min_value=1, max_value=10, value=int(st.session_state.settings.get("date_count", 3)))
        
        current_labels = st.session_state.settings.get("date_labels", "発芽日,開花日,収穫日").split(",")
        new_labels = []
        for i in range(date_count):
            default_lbl = current_labels[i] if i < len(current_labels) else f"日付{i+1}"
            new_labels.append(st.text_input(f"日付項目 {i+1} (内部列名: date_{i+1})", value=default_lbl))
            
        st.divider()
        st.write("📍 試験エリア番号の設定")
        area_opts_str = st.text_area("エリア番号のプルダウン中身（カンマ区切りで入力）", value=st.session_state.settings.get("area_options", "1,2,3,4,5,6,7,8,9,10,11,12"))
        
        save_settings = st.form_submit_button("💾 設定を保存して適用", type="primary")
        
        if save_settings:
            new_settings = {
                "crop_name": new_crop,
                "emoji": new_emoji,
                "date_count": str(date_count),
                "date_labels": ",".join(new_labels),
                "area_options": area_opts_str
            }
            st.session_state.settings = new_settings
            df_settings = pd.DataFrame(list(new_settings.items()), columns=["key", "value"])
            conn.update(worksheet="Settings", data=df_settings)
            st.success("✅ 設定をスプレッドシートに保存しました。画面を更新します。")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.subheader("🖨️ 印刷用QRコードシート作成 (A4 PDF)")
    st.write("指定した番号とサイズのQRコードをA4サイズに敷き詰めたPDFを作成します。")
    
    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        qr_start = st.number_input("開始番号", min_value=1, value=1)
    with col_q2:
        qr_end = st.number_input("終了番号", min_value=1, value=20)
    with col_q3:
        qr_size = st.number_input("QRコードサイズ (mm)", min_value=10, max_value=100, value=30)
        
    if st.button("📄 QRコードシートを作成", type="primary"):
        with st.spinner("PDFを生成中..."):
            dpi = 300
            mm_to_px = dpi / 25.4
            a4_w_px, a4_h_px = int(210 * mm_to_px), int(297 * mm_to_px)
            qr_size_px = int(qr_size * mm_to_px)
            margin_px = int(10 * mm_to_px)
            
            top_padding = int(15 * mm_to_px)
            bottom_padding = int(5 * mm_to_px)
            tag_w_px = qr_size_px + int(10 * mm_to_px)
            tag_h_px = qr_size_px + top_padding + bottom_padding
            
            usable_w = a4_w_px - margin_px * 2
            usable_h = a4_h_px - margin_px * 2
            cols = usable_w // tag_w_px
            rows = usable_h // tag_h_px
            
            if cols == 0 or rows == 0:
                st.error("指定されたQRコードサイズが大きすぎてA4に配置できません。サイズを小さくしてください。")
            else:
                pages = []
                current_page = Image.new("RGB", (a4_w_px, a4_h_px), "white")
                draw_page = ImageDraw.Draw(current_page)
                
                # ★条件①: フォント取得処理を確実化し、文字サイズを特大（QRサイズの約40%）に設定
                font_size = int(qr_size_px * 0.40)
                
                def get_large_font(size):
                    font_paths = [
                        "arial.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                        "/System/Library/Fonts/Helvetica.ttc",
                        "C:\\Windows\\Fonts\\arial.ttf"
                    ]
                    for path in font_paths:
                        try:
                            return ImageFont.truetype(path, size)
                        except Exception:
                            continue
                    try:
                        return ImageFont.load_default(size=size)
                    except TypeError:
                        return ImageFont.load_default()
                
                font = get_large_font(font_size)
                
                x_idx, y_idx = 0, 0
                for i in range(qr_start, qr_end + 1):
                    tag_str = str(i)
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_H,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(tag_str)
                    qr.make(fit=True)
                    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                    qr_img = qr_img.resize((qr_size_px, qr_size_px))
                    
                    # --- QRコード中央へ特大文字の描画 ---
                    draw_qr = ImageDraw.Draw(qr_img)
                    try:
                        text_bbox = draw_qr.textbbox((0, 0), tag_str, font=font)
                        text_w = text_bbox[2] - text_bbox[0]
                        text_h = text_bbox[3] - text_bbox[1]
                    except AttributeError:
                        text_w, text_h = draw_qr.textsize(tag_str, font=font)
                    
                    text_x = (qr_size_px - text_w) // 2
                    text_y = (qr_size_px - text_h) // 2
                    
                    # 文字の中央領域を白枠で背景クリアして巨大文字を描画
                    bg_pad_x = int(text_w * 0.2) + 10
                    bg_pad_y = int(text_h * 0.2) + 10
                    draw_qr.rectangle(
                        [text_x - bg_pad_x, text_y - bg_pad_y, text_x + text_w + bg_pad_x, text_y + text_h + bg_pad_y],
                        fill="white",
                        outline="black",
                        width=2
                    )
                    draw_qr.text((text_x, text_y), tag_str, fill="black", font=font)
                    
                    # --- ページへ貼り付けとタグ枠の描画 ---
                    x = margin_px + x_idx * tag_w_px + int(5 * mm_to_px)
                    y = margin_px + y_idx * tag_h_px + top_padding
                    current_page.paste(qr_img, (x, y))
                    
                    # 外枠およびパンチ穴ガイド
                    draw_page.rectangle([x - int(5 * mm_to_px), y - top_padding, x + qr_size_px + int(5 * mm_to_px), y + qr_size_px + bottom_padding], outline="gray")
                    draw_page.ellipse([x + qr_size_px//2 - 10, y - top_padding + 10, x + qr_size_px//2 + 10, y - top_padding + 30], outline="black")
                    
                    x_idx += 1
                    if x_idx >= cols:
                        x_idx = 0
                        y_idx += 1
                        if y_idx >= rows:
                            pages.append(current_page)
                            current_page = Image.new("RGB", (a4_w_px, a4_h_px), "white")
                            draw_page = ImageDraw.Draw(current_page)
                            x_idx, y_idx = 0, 0
                
                if x_idx > 0 or y_idx > 0:
                    pages.append(current_page)
                
                pdf_bytes = BytesIO()
                pages[0].save(pdf_bytes, format="PDF", save_all=True, append_images=pages[1:])
                st.download_button(
                    label="📥 作成したQRコードシート(PDF)をダウンロード",
                    data=pdf_bytes.getvalue(),
                    file_name=f"qr_tags_{qr_start}_to_{qr_end}.pdf",
                    mime="application/pdf"
                )
