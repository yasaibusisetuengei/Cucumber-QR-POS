import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import cv2
import numpy as np
import urllib.request
import time
import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import streamlit.components.v1 as components

# ==========================================
# 🌟 定数および初期設定
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
COLOR_THICKNESS_HEAD = (255, 0, 255) # 紫 (頭)
COLOR_THICKNESS_TAIL = (255, 128, 0) # オレンジ (尻)

# 作物マスター定義（選択肢と絵文字）
CROP_OPTIONS = {
    "キュウリ": "🥒",
    "トマト（作成中）": "🍅",
    "ナス（作成中）": "🍆",
    "イチゴ（作成中）": "🍓",
}

SAMPLE1_URL = "https://raw.githubusercontent.com//yasaibusisetuengei/Cucumber-QR-POS/main/sample/sample1.png"
SAMPLE2_URL = "https://raw.githubusercontent.com//yasaibusisetuengei/Cucumber-QR-POS/main/sample/sample2.jpg"

FONT_PATHS = [
    "arialbd.ttf", "arial.ttf",
    "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
]

st.set_page_config(page_title="管理＆判定システム", layout="wide")

st.markdown("""
    <style>
    /* カメラコンテナ本体および内部の全divのサイズ固定・切り抜き処理を解除 */
    [data-testid="stCameraInput"],
    [data-testid="stCameraInput"] > div,
    [data-testid="stCameraInput"] div {
        width: 100% !important;
        max-width: 100% !important;
        height: auto !important;
        overflow: visible !important;
    }

    /* 映像・画像本体の描画設定 */
    [data-testid="stCameraInput"] video,
    [data-testid="stCameraInput"] img {
        width: 100% !important;
        height: auto !important;
        max-height: 75vh !important;
        object-fit: contain !important;
        display: block !important;
        margin: 0 auto !important;
    }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 🌟 ヘルパー関数 (ユーティリティ & データベース)
# ==========================================
def load_settings() -> dict:
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

def play_notification_sound():
    js_code = """
    <script>
    try {
        if (navigator.vibrate) { navigator.vibrate([150, 100, 150]);
        }
        var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') { audioCtx.resume(); }
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

def get_image_bytes_from_url(url: str):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        st.error(f"サンプル画像の読み込みに失敗しました: {e}")
        return None

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
        'grade_image': [""]
    }
    
    for i in range(1, 11):
        new_item[f'date_{i}'] = [""]
        new_item[f'date_{i}_image'] = [""]
        
    new_item_df = pd.DataFrame(new_item)
    items_df = pd.concat([items_df, new_item_df], ignore_index=True)
    
    conn.update(worksheet="Tags", data=tags_df)
    conn.update(worksheet="Items", data=items_df)
    st.cache_data.clear()
    return item_code

def update_item_record(item_code, **kwargs):
    if not item_code:
        return
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
    if file_bytes is None: return None
    img = cv2.imdecode(file_bytes, 1)
    if img is None: return None
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return str(data).strip() if data else None

def sync_record_image(item_code, filename, file_bytes):
    code = item_code
    if not code and file_bytes is not None:
        tag_id = read_qr_from_bytes(file_bytes)
        if tag_id:
            code = get_tag_info(tag_id) or register_new_item(tag_id)
            
    if code and filename:
        target_col = "date_1_image"
        items_df = load_items()
        
        if items_df is not None and not items_df.empty:
            items_df['item_code'] = items_df['item_code'].astype(str)
            match = items_df[items_df['item_code'] == str(code)]
            if not match.empty:
                item_data = match.iloc[0].to_dict()
                try:
                    date_count = int(st.session_state.settings.get("date_count", 3))
                except Exception:
                    date_count = 3
                
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                
                for i in range(1, date_count + 1):
                    d_val = str(item_data.get(f'date_{i}', '')).strip()
                    if d_val == today_str:
                        target_col = f"date_{i}_image"
                        break
                else:
                    for i in range(1, date_count + 1):
                        d_val = str(item_data.get(f'date_{i}', '')).strip()
                        if d_val in ["", "nan", "None"]:
                            target_col = f"date_{i}_image"
                            break

        update_item_record(code, **{target_col: filename})
        st.toast(f"📱 画像名「{filename}」を {target_col} 列に反映しました！")

def sync_grade_image(item_code, filename, file_bytes):
    code = item_code
    if not code and file_bytes is not None:
        tag_id = read_qr_from_bytes(file_bytes)
        if not tag_id:
            img = cv2.imdecode(file_bytes, 1)
            if img is not None:
                warped, err = detect_and_warp(img)
                if not err and warped is not None:
                    detector = cv2.QRCodeDetector()
                    data, _, _ = detector.detectAndDecode(cv2.cvtColor(warped, cv2.RGB2BGR))
                    tag_id = str(data).strip() if data else None
        if tag_id:
            code = get_tag_info(tag_id) or register_new_item(tag_id)
            
    if code and filename:
        update_item_record(code, grade_image=filename)
        st.toast(f"📱 画像名「{filename}」を grade_image 列に反映しました！")
    elif not code:
        st.toast("⚠️ QRコードが検出できなかったため、画像名の保存は保留されました。")

# ==========================================
# 🌟 OpenCV 画像処理・計測関数
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

def extract_cucumber_contour(warped_img: np.ndarray, crop_name: str = "作物"):
    hsv = cv2.cvtColor(warped_img, cv2.COLOR_RGB2HSV)
    lower_green, upper_green = np.array([35, 40, 40]), np.array([85, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: 
        return None, f"{crop_name}が検出できません。"
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
    if hp1 is not None and hp2 is not None: cv2.line(res, tuple(hp1.astype(int)), tuple(hp2.astype(int)), COLOR_THICKNESS_HEAD, 3)
    if tp1 is not None and tp2 is not None: cv2.line(res, tuple(tp1.astype(int)), tuple(tp2.astype(int)), COLOR_THICKNESS_TAIL, 3)
    return res

def process_measurement(image, crop_name="キュウリ"):
    if image is None: return None, "画像がありません", None, None, None, None, None
    warped, err = detect_and_warp(image)
    if err: return image, f"<h3 style='color:red;'>{err}</h3>", None, None, None, None, None
    contour, err = extract_cucumber_contour(warped, crop_name)
    if err: return warped, f"<h3 style='color:red;'>{err}</h3>", None, None, None, None, None
    
    length_cm, end1, end2 = calculate_length(contour)
    curve_cm, ds, de, cp, foot = calculate_curve(contour)
    
    # ==== 修正箇所: 両端の太さを計測し、太い方を頭・細い方を尻にする ====
    thick1_cm, p1_1, p1_2 = calculate_thickness(end1, end2, DIST_5CM_PX, contour)
    thick2_cm, p2_1, p2_2 = calculate_thickness(end2, end1, DIST_5CM_PX, contour)

    if thick1_cm >= thick2_cm:
        head_thick_cm, hp1, hp2 = thick1_cm, p1_1, p1_2
        tail_thick_cm, tp1, tp2 = thick2_cm, p2_1, p2_2
    else:
        head_thick_cm, hp1, hp2 = thick2_cm, p2_1, p2_2
        tail_thick_cm, tp1, tp2 = thick1_cm, p1_1, p1_2
    # ====================================================================

    # ==== 実測値と予測値の比較データに基づく補正処理 ====
    length_cm = length_cm * 0.916
    head_thick_cm = head_thick_cm * 1.001
    tail_thick_cm = tail_thick_cm * 0.992
    curve_cm = curve_cm * 0.832
    # ====================================================

    avg_thick_cm = (head_thick_cm + tail_thick_cm) / 2.0 if head_thick_cm > 0 else 1.5

    grade, display_grade = evaluate_grade(length_cm, curve_cm, head_thick_cm, tail_thick_cm)
    rank_bg = {"A":"#e8f5e9", "B":"#fff3cd", "C":"#f8d7da"}.get(grade, "#f8f9fa")
    
    res_img = draw_results(warped, contour, ds, de, cp, foot, hp1, hp2, tp1, tp2)
    
    html = f"""
    <div style="background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; color: black;">
        <h3 style="text-align: center; margin-top: 0; color: #2e7d32;">📐 計測・判定結果 ({crop_name})</h3>
        <p>🟨 <b>長さ（黄色い線の長さ）:</b> {length_cm:.1f} cm</p>
        <p>🟪 <b>頭の太さ（紫の線の長さ）:</b> {head_thick_cm:.1f} cm</p>
        <p>🟧 <b>尻の太さ（オレンジの線の長さ）:</b> {tail_thick_cm:.1f} cm</p>
        <p>🟥 <b>曲がり（赤い線の長さ）:</b> {curve_cm:.1f} cm</p>
        <div style="background-color: {rank_bg}; padding: 12px; text-align: center; font-size: 1.2em; border-radius: 8px; margin-top: 10px;">
            <b>階級: {display_grade}</b>
        </div>
    </div>
    """
    return res_img, html, length_cm, avg_thick_cm, curve_cm, display_grade, warped

# ==========================================
# 🌟 PDF生成用ヘルパー関数
# ==========================================
def get_large_font(font_size: int):
    font_targets = [
        "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc", "msgothic.ttc"
    ]
    for font_name in font_targets:
        try:
            return ImageFont.truetype(font_name, font_size)
        except IOError:
            continue
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()

def generate_qr_pdf(qr_start: int, qr_end: int, qr_size_mm: int) -> bytes | None:
    dpi = 300
    mm_to_px = dpi / 25.4
    a4_w_px, a4_h_px = int(210 * mm_to_px), int(297 * mm_to_px)
    qr_size_px = int(qr_size_mm * mm_to_px)
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
        return None

    # ====== 配置全体を中央に寄せるための開始座標を計算 ======
    total_w_px = cols * tag_w_px
    total_h_px = rows * tag_h_px
    start_x_px = (a4_w_px - total_w_px) // 2
    start_y_px = (a4_h_px - total_h_px) // 2
    # ================================================================

    pages = []
    page_data = []

    font_size = max(10, int(qr_size_px * 0.30))
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

        page_data.append({
            "x_idx": x_idx, "y_idx": y_idx, "tag_str": tag_str, "qr_img": qr_img
        })

        x_idx += 1
        if x_idx >= cols:
            x_idx = 0
            y_idx += 1

        if y_idx >= rows or i == qr_end:
            front_page = Image.new("RGB", (a4_w_px, a4_h_px), "white")
            back_page = Image.new("RGB", (a4_w_px, a4_h_px), "white")
            draw_front = ImageDraw.Draw(front_page)
            draw_back = ImageDraw.Draw(back_page)

            for item in page_data:
                # 表面の座標計算
                fx = start_x_px + item["x_idx"] * tag_w_px + int(5 * mm_to_px)
                fy = start_y_px + item["y_idx"] * tag_h_px + top_padding
              
                front_page.paste(item["qr_img"], (fx, fy))
                draw_front.rectangle([
                    fx - int(5 * mm_to_px), fy - top_padding,
                    fx + qr_size_px + int(5 * mm_to_px), fy + qr_size_px + bottom_padding
                ], outline="gray")
                draw_front.ellipse([
                    fx + qr_size_px // 2 - 10, fy - top_padding + 10,
                    fx + qr_size_px // 2 + 10, fy - top_padding + 30
                ], outline="black")

                # 裏面の座標計算
                bx_idx = cols - 1 - item["x_idx"]
                bx = start_x_px + bx_idx * tag_w_px + int(5 * mm_to_px)
                by = start_y_px + item["y_idx"] * tag_h_px + top_padding
                draw_back.rectangle([
                    bx - int(5 * mm_to_px), by - top_padding,
                    bx + qr_size_px + int(5 * mm_to_px), by + qr_size_px + bottom_padding
                ], outline="gray")
                draw_back.ellipse([
                    bx + qr_size_px // 2 - 10, by - top_padding + 10,
                    bx + qr_size_px // 2 + 10, by - top_padding + 30
                ], outline="black")

                center_x = bx + qr_size_px // 2
                center_y = by + qr_size_px // 2
                draw_back.text((center_x, center_y), item["tag_str"], fill="black", font=font, anchor="mm")

            pages.append(front_page)
            pages.append(back_page)
            page_data = []
            x_idx, y_idx = 0, 0

    pdf_bytes = BytesIO()
    if pages:
        pages[0].save(pdf_bytes, format="PDF", save_all=True, append_images=pages[1:])
    return pdf_bytes.getvalue()

# ==========================================
# 🌟 アプリケーション セッション初期化
# ==========================================
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
# 🌟 Streamlit UI 構成 (3つのタブ)
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
            img_key = hash(qr_img.getvalue())
            if "record_img_id" not in st.session_state or st.session_state.record_img_id != img_key:
                st.session_state.record_img_id = img_key
                st.session_state.record_img_filename = f"scan_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                st.session_state.temp_record_bytes = qr_img.getvalue()

        if "temp_record_bytes" in st.session_state and st.session_state.temp_record_bytes:
            file_bytes_qr = np.asarray(bytearray(st.session_state.temp_record_bytes), dtype=np.uint8)
            cam_tag = read_qr_from_bytes(file_bytes_qr)
            cam_item_code = get_tag_info(cam_tag) if cam_tag else None
       
            st.download_button(
                label="💾 撮影画像をスマホに保存",
                data=st.session_state.temp_record_bytes,
                file_name=st.session_state.record_img_filename,
                mime="image/jpeg",
                key="dl_cam_qr",
                on_click=sync_record_image,
                args=(cam_item_code, st.session_state.record_img_filename, file_bytes_qr)
            )
            
    elif img_source_qr == "アップロード":
        qr_img = st.file_uploader("QRコード画像を選択", type=["jpg", "jpeg", "png"], key="qr_upload")
        if qr_img: 
            file_bytes_qr = np.asarray(bytearray(qr_img.read()), dtype=np.uint8)
            st.session_state.record_img_filename = qr_img.name
    else:
        st.info("サンプル画像 (sample1.png) を使用します。")
        raw_data = get_image_bytes_from_url(SAMPLE1_URL)
        if raw_data: 
            file_bytes_qr = np.asarray(bytearray(raw_data), dtype=np.uint8)
            st.session_state.record_img_filename = "sample1.png"

    if file_bytes_qr is not None:
        if img_source_qr in ["アップロード", "サンプル画像 (sample1)"]:
            cv_img_qr = cv2.imdecode(file_bytes_qr, 1)
            st.image(cv2.cvtColor(cv_img_qr, cv2.COLOR_BGR2RGB), use_container_width=True)
            
        tag_id = read_qr_from_bytes(file_bytes_qr)
        
        if tag_id:
            if st.session_state.last_scanned_tag != tag_id:
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
                    except Exception: pass
                return None

            date_count = int(st.session_state.settings.get("date_count", 3))
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            
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
                    target_idx = 1
                    for i in range(1, date_count + 1):
                        if not clean_date_str(item_data.get(f'date_{i}', '')):
                            update_kwargs[f'date_{i}'] = today_str
                            update_kwargs[f'date_{i}_image'] = st.session_state.get('record_img_filename', '')
                            updated = True
                            target_idx = i
                            break
                    
                    if updated:
                        update_item_record(item_code, **update_kwargs)
                        st.success(f"🌱 スキャンを検知し、自動でデータベースを更新しました！ (画像名: {update_kwargs[f'date_{target_idx}_image']})")
                        match = load_items().query(f"item_code == '{item_code}'")
                        item_data = match.iloc[0].to_dict() if not match.empty else {}
        
                st.session_state.processed_qrs.add(tag_id)

            st.write(f"📝 編集対象コード: `{item_code}`")
            
            area_opts = [x.strip() for x in st.session_state.settings.get("area_options", "1").split(",") if x.strip()]
            current_area = clean_date_str(item_data.get('area_number', area_opts[0] if area_opts else "1"))
            if current_area not in area_opts: area_opts.insert(0, current_area)
        
            new_area = st.selectbox("試験エリア番号", area_opts, index=area_opts.index(current_area))
            
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
                    d_str = val.strftime("%Y-%m-%d") if val else ""
                    update_kwargs[f"date_{i+1}"] = d_str
                    if d_str and st.session_state.get('record_img_filename'):
                        update_kwargs[f"date_{i+1}_image"] = st.session_state.get('record_img_filename', '')
                
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
                img_key = hash(c_img.getvalue())
                if "grade_img_id" not in st.session_state or st.session_state.grade_img_id != img_key:
                    st.session_state.grade_img_id = img_key
                    st.session_state.grade_img_filename = f"grade_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    st.session_state.temp_grade_bytes = c_img.getvalue()

            if "temp_grade_bytes" in st.session_state and st.session_state.temp_grade_bytes:
                file_bytes_grade = np.asarray(bytearray(st.session_state.temp_grade_bytes), dtype=np.uint8)
                cam_tag_g = read_qr_from_bytes(file_bytes_grade)
                cam_item_code_g = get_tag_info(cam_tag_g) if cam_tag_g else None
                
                st.download_button(
                    label="💾 撮影画像をスマホに保存",
                    data=st.session_state.temp_grade_bytes,
                    file_name=st.session_state.grade_img_filename,
                    mime="image/jpeg",
                    key="dl_cam_grade",
                    on_click=sync_grade_image,
                    args=(cam_item_code_g, st.session_state.grade_img_filename, file_bytes_grade)
                )

        elif img_source_grade == "アップロード":
            c_img = st.file_uploader("画像を選択", type=["jpg", "jpeg", "png"], key="grade_upload", on_change=clear_grade_result)
            
            if c_img: 
                file_bytes_grade = np.asarray(bytearray(c_img.read()), dtype=np.uint8)
                st.session_state.grade_img_filename = c_img.name
        else:
            st.info("サンプル画像 (sample2.jpg) を使用します。")
            raw_data = get_image_bytes_from_url(SAMPLE2_URL)
            if raw_data: 
                file_bytes_grade = np.asarray(bytearray(raw_data), dtype=np.uint8)
                st.session_state.grade_img_filename = "sample2.jpg"

        if file_bytes_grade is not None and img_source_grade in ["アップロード", "サンプル画像 (sample2)"]:
            cv_img_grade_preview = cv2.imdecode(file_bytes_grade, 1)
            st.image(cv2.cvtColor(cv_img_grade_preview, cv2.COLOR_BGR2RGB), use_container_width=True)

        grade_btn = st.button("📏 計測して階級を判定", type="primary")

    with col2:
        if grade_btn and file_bytes_grade is not None:
            if c_name == "キュウリ":
                cv_img = cv2.imdecode(file_bytes_grade, 1)
                cv_img_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                res_img, html, l_cm, t_cm, c_cm, grade_str, warped = process_measurement(cv_img_rgb, c_name)
                
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
            else:
                st.info(f"💡 現在「{c_name}」の画像解析・階級判定ロジックは準備中です。キュウリの計測を行う場合は初期設定で「キュウリ」を選択してください。")

        if st.session_state.grade_result is not None:
            res = st.session_state.grade_result
            if res['res_img'] is not None: st.image(res['res_img'], channels="RGB")
            if res['html']: st.markdown(res['html'], unsafe_allow_html=True)
            
            if res['l_cm'] is not None:
                if res['tag_id']:
                    if st.session_state.last_scanned_tag != res['tag_id']:
                        play_notification_sound()
                        st.session_state.last_scanned_tag = res['tag_id']
                        
                    st.success(f"✅ タグ【{res['tag_id']}】を検出しました。重さを入力して登録を完了させてください。")
                    with st.form("register_grade_form"):
                        harvest_weight = st.number_input("重さ (g)", min_value=0.0, step=1.0, value=0.0)
                        submitted = st.form_submit_button("💾 結果をDBに登録する")
                        if submitted:
                            item_code = get_tag_info(res['tag_id'])
                            if not item_code:
                                item_code = register_new_item(res['tag_id'])
                                st.info("新しいアイテムとして登録しました。")
                            update_item_record(
                                item_code,
                                length=round(res['l_cm'], 1),
                                thickness=round(res['t_cm'], 1),
                                curve=round(res['c_cm'], 1),
                                grade=res['grade_str'],
                                weight=round(harvest_weight, 1),
                                grade_image=st.session_state.get('grade_img_filename', '')
                            )
                            st.success(f"🎉 判定結果と重さを {item_code} に記録しました！")
                else:
                    st.warning("⚠️ QRコードが検出できませんでした。A4ボード上のQRコードがカメラに明確に写っているか確認してください。")

# --- タブ3: 初期設定 (設定変更 & QR発行) ---
with tab3:
    st.header("⚙️ システム初期設定")
    
    st.subheader("システム・マスター設定")
    current_crop = st.session_state.settings.get("crop_name", "キュウリ")
    new_crop = st.selectbox("対象作物を選択", list(CROP_OPTIONS.keys()), index=list(CROP_OPTIONS.keys()).index(current_crop) if current_crop in CROP_OPTIONS else 0)
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        new_date_count = st.number_input("記録する日付の数（例: 発芽、開花、収穫なら3）", min_value=1, max_value=10, value=int(st.session_state.settings.get("date_count", 3)))
    with col_d2:
        default_labels = "発芽日,開花日,収穫日"
        if new_date_count != 3:
            default_labels = ",".join([f"日付{i+1}" for i in range(new_date_count)])
        new_date_labels = st.text_input("日付のラベル名（カンマ区切り）", value=st.session_state.settings.get("date_labels", default_labels))
        
    new_area_opts = st.text_input("試験エリア番号の選択肢（カンマ区切り）", value=st.session_state.settings.get("area_options", "1,2,3,4,5,6,7,8,9,10,11,12"))
    
    if st.button("💾 設定を保存"):
        new_settings = {
            "crop_name": new_crop,
            "emoji": CROP_OPTIONS[new_crop],
            "date_count": str(new_date_count),
            "date_labels": new_date_labels,
            "area_options": new_area_opts
        }
        df = pd.DataFrame(list(new_settings.items()), columns=["key", "value"])
        conn.update(worksheet="Settings", data=df)
        st.session_state.settings = new_settings
        st.success("✅ 設定を更新しました！（反映にはページリロードが必要な場合があります）")
        st.rerun()

    st.markdown("---")
    st.subheader("🏷️ 物理タグ (QRコード) PDF 発行")
    st.write("A4用紙の両面に印刷できるタグ（QRコード）のPDFを生成します。")
    st.write("※ 表面・裏面の2ページ構成で生成されます。印刷時に**「両面印刷」「実際のサイズ（100%）」**を選択してください。")
    st.write("※ 余白の設定によってはズレが生じる場合があります。必要に応じて試し刷りを行ってください。")

    col1, col2, col3 = st.columns(3)
    with col1: qr_start = st.number_input("開始番号", min_value=1, value=1, step=1)
    with col2: qr_end = st.number_input("終了番号", min_value=1, value=40, step=1)
    with col3: qr_size = st.number_input("QRサイズ (mm)", min_value=10, max_value=50, value=25, step=1)

    if st.button("📄 PDFを生成", type="primary"):
        if qr_start > qr_end:
            st.error("開始番号は終了番号以下にしてください。")
        else:
            with st.spinner("PDFを生成中..."):
                pdf_data = generate_qr_pdf(qr_start, qr_end, qr_size)
                if pdf_data:
                    st.success("✅ PDFの生成が完了しました！")
                    st.download_button(
                        label="📥 PDFをダウンロード",
                        data=pdf_data,
                        file_name=f"QR_Tags_{qr_start}_to_{qr_end}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.error("PDFの生成に失敗しました。サイズ設定等を見直してください。")

    st.markdown("---")
    st.subheader("🗑️ データベース管理")
    
    st.write("▼ 全タグの紐付け解除（Itemsデータは残ります）")
    if st.button("🚨 全タグの紐付けを解除", type="secondary"):
        tags_df = load_tags()
        if tags_df is not None and not tags_df.empty:
            tags_df['current_item_code'] = ""
            conn.update(worksheet="Tags", data=tags_df)
            st.cache_data.clear()
            st.success("✅ 全てのタグの紐付けをリセットしました！")
        else:
            st.info("解除するタグ情報がありません。")

    st.write("▼ 全Itemsレコード削除（Tagsの紐付けも解除されます）")
    if st.button("🚨 全Itemsレコードを削除", type="primary"):
        empty_items_df = pd.DataFrame(columns=[
            'item_code', 'weight', 'area_number', 'comment', 'grade',
            'length', 'thickness', 'curve', 'grade_image',
            'date_1', 'date_2', 'date_3', 'date_4', 'date_5', 'date_6', 'date_7', 'date_8', 'date_9', 'date_10',
            'date_1_image', 'date_2_image', 'date_3_image', 'date_4_image', 'date_5_image', 'date_6_image', 'date_7_image', 'date_8_image', 'date_9_image', 'date_10_image'
        ])
        conn.update(worksheet="Items", data=empty_items_df)
        
        tags_df = load_tags()
        if tags_df is not None and not tags_df.empty:
            tags_df['current_item_code'] = ""
            conn.update(worksheet="Tags", data=tags_df)
        
        st.cache_data.clear()
        st.success("✅ 全てのItemsレコードを削除し、タグの紐付けをリセットしました！")

st.markdown("---")
st.markdown("<p style='text-align: center; color: #888;'>作物管理＆判定システム v2.0</p>", unsafe_allow_html=True)
