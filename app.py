import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import cv2
import numpy as np

# --- ページ設定とデータベース接続 ---
st.set_page_config(page_title="🥒 キュウリ管理＆判定システム", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

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
    df = conn.read(worksheet="Tags", ttl=0, dtype=str)
    return df.fillna("")

def load_items():
    df = conn.read(worksheet="Items", ttl=0, dtype=str)
    # 🌟 修正: 数値列は0.0で、それ以外の文字列表は空文字("")で埋めるように修正
    for col in ['weight', 'length', 'thickness', 'curve']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    for col in df.columns:
        if col not in ['weight', 'length', 'thickness', 'curve']:
            df[col] = df[col].fillna("")
    return df

def get_tag_info(tag_id):
    tags_df = load_tags()
    tags_df['tag_id'] = tags_df['tag_id'].astype(str)
    match = tags_df[tags_df['tag_id'] == str(tag_id)]
    if not match.empty:
        code = match.iloc[0]['current_item_code']
        if code != "": return str(code)
    return None

def register_new_item(tag_id):
    tags_df = load_tags()
    items_df = load_items()
    tags_df['tag_id'] = tags_df['tag_id'].astype(str)
    
    item_code = f"ITEM-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if str(tag_id) in tags_df['tag_id'].values:
        tags_df.loc[tags_df['tag_id'] == str(tag_id), 'current_item_code'] = item_code
    else:
        new_tag = pd.DataFrame({'tag_id': [str(tag_id)], 'current_item_code': [item_code]})
        tags_df = pd.concat([tags_df, new_tag], ignore_index=True)
        
    new_item = pd.DataFrame({
        'item_code': [item_code], 'sprout_date': [""], 'bloom_date': [""], 'weight': [0.0],
        'area_number': ["1"], 'comment': [""], 'grade': [""], 'length': [0.0], 'thickness': [0.0], 'curve': [0.0]
    })
    items_df = pd.concat([items_df, new_item], ignore_index=True)
    
    conn.update(worksheet="Tags", data=tags_df)
    conn.update(worksheet="Items", data=items_df)
    return item_code

def update_item_record(item_code, **kwargs):
    items_df = load_items()
    items_df['item_code'] = items_df['item_code'].astype(str)
    idx = items_df[items_df['item_code'] == str(item_code)].index
    
    if not idx.empty:
        for key, val in kwargs.items():
            if key not in items_df.columns:
                items_df[key] = ""
            # 🌟 修正: Pandasの厳格な型チェックを回避するため、object型に変換してから代入
            items_df[key] = items_df[key].astype(object)
            items_df.loc[idx, key] = val
            
        conn.update(worksheet="Items", data=items_df)

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
    if not contours: return None, "キュウリが検出できません。"
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
# 4. Streamlit UI 構成 (タブ切り替え)
# ==========================================
tab1, tab2 = st.tabs(["🌱 生育記録", "🥒 収穫・階級判定"])

# --- タブ1: 生育記録 ---
with tab1:
    st.header("🌱 生育記録 (QRスキャン)")
    
    img_source_qr = st.radio("入力方法", ["カメラ", "アップロード"], key="qr_radio")
    if img_source_qr == "カメラ":
        qr_img = st.camera_input("QRコードを撮影", key="qr_camera")
    else:
        qr_img = st.file_uploader("QRコード画像を選択", type=["jpg", "jpeg", "png"], key="qr_upload")
    
    if qr_img is not None:
        file_bytes = np.asarray(bytearray(qr_img.read()), dtype=np.uint8)
        tag_id = read_qr_from_bytes(file_bytes)
        
        if tag_id:
            st.success(f"🏷️ タグを認識しました: {tag_id}")
            item_code = get_tag_info(tag_id)
            if not item_code:
                item_code = register_new_item(tag_id)
                st.info("新しいアイテムとして登録しました。")
            
            items_df = load_items()
            match = items_df[items_df['item_code'] == item_code]
            item_data = match.iloc[0].to_dict() if not match.empty else {}
            
            with st.form("growth_record_form"):
                st.write(f"📝 編集対象コード: `{item_code}`")
                
                area_opts = [str(i) for i in range(1, 13)]
                current_area = str(item_data.get('area_number', "1"))
                if current_area not in area_opts: current_area = "1"
                
                col_a, col_b = st.columns(2)
                with col_a:
                    area = st.selectbox("試験エリア番号", area_opts, index=area_opts.index(current_area))
                    sprout = st.date_input("発芽日", value=pd.to_datetime(item_data.get('sprout_date')).date() if item_data.get('sprout_date') else None)
                with col_b:
                    bloom = st.date_input("開花日", value=pd.to_datetime(item_data.get('bloom_date')).date() if item_data.get('bloom_date') else None)
                    weight = st.number_input("重さ (g)", value=float(item_data.get('weight', 0.0)))
                
                comment = st.text_area("コメント（自由入力）", value=str(item_data.get('comment', '')))
                
                if st.form_submit_button("記録を更新する"):
                    # 🌟 修正: 型を明示的に指定して更新関数に渡す
                    update_item_record(
                        item_code, 
                        sprout_date=sprout.strftime("%Y-%m-%d") if sprout else "",
                        bloom_date=bloom.strftime("%Y-%m-%d") if bloom else "",
                        weight=float(weight),
                        area_number=str(area),
                        comment=str(comment)
                    )
                    st.success("データベースを更新しました！")
        else:
            st.error("QRコードを検出できませんでした。別の画像を選択するか、再撮影してください。")

# --- タブ2: 収穫・階級判定 ---
with tab2:
    st.header("🥒 収穫・階級判定")
    
    col1, col2 = st.columns(2)
    with col1:
        img_source_grade = st.radio("画像入力", ["カメラ", "アップロード"], key="grade_radio")
        if img_source_grade == "カメラ":
            c_img = st.camera_input("キュウリを撮影（A4マーカー枠＆QRコード必須）", key="grade_camera")
        else:
            c_img = st.file_uploader("画像を選択", type=["jpg", "jpeg", "png"], key="grade_upload")
        
        grade_btn = st.button("📏 計測＆DB登録", type="primary")

    with col2:
        if grade_btn and c_img is not None:
            file_bytes = np.asarray(bytearray(c_img.read()), dtype=np.uint8)
            cv_img = cv2.imdecode(file_bytes, 1)
            cv_img_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            
            # 計測処理の実行
            res_img, html, l_cm, t_cm, c_cm, grade_str, warped = process_measurement(cv_img_rgb)
            
            if res_img is not None: st.image(res_img, channels="RGB")
            st.markdown(html, unsafe_allow_html=True)
            
            if l_cm is not None:
                tag_id = read_qr_from_bytes(file_bytes)
                
                if not tag_id and warped is not None:
                    detector = cv2.QRCodeDetector()
                    warped_bgr = cv2.cvtColor(warped, cv2.COLOR_RGB2BGR)
                    data, _, _ = detector.detectAndDecode(warped_bgr)
                    tag_id = str(data).strip() if data else None
                
                if tag_id:
                    item_code = get_tag_info(tag_id)
                    # 🌟 修正: 小数はfloat、文字列はstrに明示的に変換して渡す
                    if item_code:
                        update_item_record(item_code, length=float(l_cm), thickness=float(t_cm), curve=float(c_cm), grade=str(grade_str))
                        st.success(f"✅ タグ【{tag_id}】を検出し、階級データ（{grade_str}）をデータベースに記録しました！")
                    else:
                        item_code = register_new_item(tag_id)
                        update_item_record(item_code, length=float(l_cm), thickness=float(t_cm), curve=float(c_cm), grade=str(grade_str))
                        st.success(f"✅ 新規タグ【{tag_id}】を登録し、階級データ（{grade_str}）を記録しました！")
                else:
                    st.error("⚠️ 画像からQRコードを検出できませんでした。計測は完了しましたが、データベースには登録されていません。QRコードがはっきり写るように撮影してください。")
