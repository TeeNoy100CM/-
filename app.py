%%writefile app.py
import streamlit as st
import socket
import pandas as pd
import folium
import base64
from streamlit_folium import st_folium
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from branca.element import Template, MacroElement
import time
from streamlit_autorefresh import st_autorefresh
import os
import pytz # อย่าลืม import เพิ่มด้านบนสุด
from datetime import datetime

def get_thai_time():
    """ดึงเวลาปัจจุบันของประเทศไทย"""
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

# ในส่วนที่ใช้บันทึกข้อมูล ให้เปลี่ยนจาก datetime.now() เป็น get_thai_time()
# ตัวอย่าง:
# "Timestamp": get_thai_time()

# ---------- ฟังก์ชันสำหรับระบบ Logging ----------
HISTORY_FILE = "status_history.csv"

def save_to_history(df):
    """บันทึกข้อมูลการสแกนลงไฟล์ CSV แบบต่อท้าย"""
    # ตรวจสอบว่ามีไฟล์อยู่แล้วหรือไม่ เพื่อเขียน Header
    file_exists = os.path.isfile(HISTORY_FILE)
    
    # เลือกเฉพาะคอลัมน์ที่จำเป็นเพื่อประหยัดพื้นที่
    log_df = df[["Label", "Status", "Timestamp", "IP"]].copy()
    
    # บันทึกแบบ Append
    log_df.to_csv(HISTORY_FILE, mode='a', index=False, header=not file_exists, encoding="utf-8-sig")


def get_status_changes():
    if not os.path.isfile(HISTORY_FILE): 
        return None
    
    df_history = pd.read_csv(HISTORY_FILE)
    
    # 1. บังคับแปลงคอลัมน์ Timestamp ให้เป็น datetime ก่อน (ป้องกัน Error)
    df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
    
    # 2. ลบแถวที่เวลาผิดพลาด (ถ้ามี)
    df_history = df_history.dropna(subset=['Timestamp'])
    
    # 3. บวก 7 ชั่วโมงเพื่อปรับเป็นเวลาไทย
    df_history['Timestamp'] = df_history['Timestamp'] + pd.Timedelta(hours=7)
    
    # 4. เรียงลำดับข้อมูล
    df_history = df_history.sort_values(['Label', 'Timestamp'])
    
    # 5. หาสถานะก่อนหน้าเพื่อเช็คการเปลี่ยนแปลง
    df_history['Prev_Status'] = df_history.groupby('Label')['Status'].shift(1)
    
    # 6. กรองเฉพาะแถวที่สถานะเปลี่ยนจริง
    changes_df = df_history[
        (df_history['Prev_Status'].notna()) & 
        (df_history['Status'] != df_history['Prev_Status'])
    ].copy()
    
    # 7. สร้างคอลัมน์ Event และ Current_Status
    changes_df['Event'] = changes_df['Prev_Status'] + " ➡️ " + changes_df['Status']
    changes_df['Current_Status'] = changes_df['Status']
    
    # 8. จัดรูปแบบการแสดงผลเวลาไทย (วัน/เดือน/ปี ชั่วโมง:นาที) และเอา 10 แถวล่าสุด
    changes_df = changes_df.sort_values('Timestamp', ascending=False)
    changes_df['Timestamp'] = changes_df['Timestamp'].dt.strftime('%d-%m-%Y %H:%M:%S')
    
    # ตัดเหลือ 10 แถวตามที่คุณต้องการ และไม่เอา IP
    return changes_df[['Timestamp', 'Label', 'Event', 'Current_Status']].head(10)

# ---------- ตั้งค่าหน้า ----------
st.set_page_config(page_title="เครื่องวัดคลื่นสั่นสะเทือนพื้นดิน", layout="wide")

# ฟอนต์ไทย
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Sarabun', sans-serif !important;
    }
    </style>
""", unsafe_allow_html=True)


# ---------- ข้อมูลจุดติดตั้ง ----------
targets_combined = [
    { "ip": "1.0.168.103", "port": 80, "lat": 13.92747, "lon": 99.08365, "label": "โรงเรียนพุน้ำร้อนรัตนคีรี (อบต.บ้านเก่า) จ.กาญจนบุรี" },
    { "ip": "101.51.144.62", "port": 800, "lat": 18.330991, "lon": 99.371529, "label": "โรงเรียนห้างฉัตรวิทยา จ.ลำปาง" },
    { "ip": "1.0.203.231", "port": 81, "lat": 9.861786, "lon": 98.831959, "label": "โรงเรียนบ้านตรัง จ.ชุมพร" },
    { "ip": "1.0.168.100", "port": 81, "lat": 11.072309, "lon": 99.417141, "label": "โรงเรียนบางสะพานน้อยวิทยาคม จ.ประจวบคีรีขันธ์" },
    { "ip": "113.53.30.245", "port": 800, "lat": 18.773, "lon": 100.756, "label": "วัดเขาน้อยเทศรังสี จ.น่าน" },
    { "ip": "1.0.168.110", "port": 8081, "lat": 15.13259, "lon": 98.44493, "label": "วัดวังก์วิเวการาม จ.กาญจนบุรี" },
    { "ip": "1.0.203.244", "port": 81, "lat": 8.86737, "lon": 98.33252, "label": "โรงเรียนตะกั่วป่าเสนานุกูล จ.พังงา" },
    { "ip": "101.51.121.195", "port": 80, "lat": 17.239593, "lon": 98.972664, "label": "เขื่อนภูมิพล จ.ตาก" },
    { "ip": "101.109.83.230", "port": 80, "lat": 20.4165, "lon": 99.8679, "label": "สำนักสงฆ์ถ้ำผาเรือ จ.เชียงราย" },
    { "ip": "1.20.140.73", "port": 80, "lat": 16.9815, "lon": 98.5234, "label": "โรงเรียนแม่ระมาดวิทยาคม จ.ตาก" },
    { "ip": "1.0.203.192", "port": 80, "lat": 7.9689, "lon": 98.3345, "label": "อ่างเก็บน้ำบางเหนียวดำ จ.ภูเก็ต" },
    { "ip": "1.20.227.186", "port": 800, "lat": 8.5550, "lon": 98.8772, "label": "โรงเรียนบ้านบางเหียน จ.กระบี่" },
    { "ip": "182.53.216.205", "port": 80, "lat": 19.3557, "lon": 100.7022, "label": "โรงเรียนไตรเขตประชาสามัคคีรัชมังคลาภิเษก จ.น่าน" },
    { "ip": "182.53.197.109", "port": 80, "lat": 18.1024, "lon": 97.9372, "label": "วิทยาลัยการอาชีพแม่สะเรียง จ.เเม่ฮองสอน" },
    { "ip": "1.0.204.197", "port": 800, "lat": 18.0232, "lon": 100.8954, "label": "โรงเรียนบ้านนาหน่ำ จ.อุตรดิตถ์" },
    { "ip": "182.53.197.55", "port": 800, "lat": 19.4077, "lon": 98.9723, "label": "โรงเรียนเชียงดาววิทยาคม จ.เชียงใหม่" },
    { "ip": "182.53.197.74", "port": 800, "lat": 18.8448, "lon": 98.7344, "label": "โรงเรียนสะเมิงพิทยาคม จ.เชียงใหม่" },
    { "ip": "182.53.197.65", "port": 80, "lat": 19.1472, "lon": 99.6078, "label": "โรงเรียนวังเหนือวิทยา จ.ลำปาง" },
    { "ip": "1.20.225.133", "port": 800, "lat": 18.83654, "lon": 97.94252, "label": "โรงเรียนขุนยวมวิทยา จ.เเม่ฮองสอน" },
    { "ip": "182.53.197.68", "port": 80, "lat": 19.52115, "lon": 98.24822, "label": "โรงเรียนปางมะผ้าพิทยาสรรพ์ จ.เเม่ฮองสอน" },
    { "ip": "182.52.68.40", "port": 800, "lat": 19.67505, "lon": 99.9279, "label": "โรงเรียนบ้านทรายงาม จ.เชียงราย" },
    { "ip": "182.53.216.172", "port": 800, "lat": 19.17153, "lon": 100.27576, "label": "โรงเรียนปงรัชดาภิเษก จ.พะเยา" },
    { "ip": "182.53.197.64", "port": 800, "lat": 18.7632, "lon": 99.9843, "label": "โรงเรียนประชารัฐธรรมคุณ จ.ลำปาง" },
    { "ip": "1.20.140.30", "port": 800, "lat": 16.4099, "lon": 99.3848, "label": "โรงเรียนนาบ่อคำวิทยาคม จ.กำเเพงเพชร" },
    { "ip": "101.51.121.167", "port": 80, "lat": 16.0329, "lon": 98.8595, "label": "โรงเรียนอุ้มผางวิทยาคม จ.ตาก" },
    { "ip": "1.0.204.225", "port": 80, "lat": 15.186391, "lon": 99.488039, "label": "โรงเรียนบ้านทุ่งน้อย จ.อุทัยธานี" },
    { "ip": "182.53.197.177", "port": 80, "lat": 20.19367, "lon": 100.22184, "label": "โรงเรียนแม่แอบวิทยาคม จ.เชียงราย" },
    { "ip": "182.53.197.73", "port": 80, "lat": 19.6838, "lon": 100.4058, "label": "โรงเรียนบ้านฮวก จ.พะเยา" },
    { "ip": "182.53.197.62", "port": 800, "lat": 20.0371, "lon": 99.2072, "label": "โรงเรียนราชประชานุเคราะห์ 30 จ.เชียงใหม่" },
    { "ip": "61.7.143.243", "port": 80, "lat": 16.7704, "lon": 101.4773, "label": "โรงเรียนบ้านห้วยระหงส์ จ.เพชรบูรณ์" },
    { "ip": "101.51.121.206", "port": 80, "lat": 15.8992, "lon": 100.9533, "label": "โรงเรียนวัดเขาเจริญธรรม จ.เพชรบูรณ์" },
    { "ip": "1.1.136.159", "port": 80, "lat": 17.1652, "lon": 101.1222, "label": "โรงเรียนบ้านแก่งครก จ.เลย" },
    { "ip": "101.51.138.55", "port": 800, "lat": 14.462368, "lon": 101.79539, "label": "โรงเรียนบ้านโคกสันติสุข จ.นครราชสีมา" },
    { "ip": "125.27.179.36", "port": 80, "lat": 14.805869, "lon": 101.044852, "label": "โรงเรียนสหพันธ์อ่างทอง จ.ลพบุรี" },
    { "ip": "125.25.57.239", "port": 80, "lat": 13.688496, "lon": 101.484074, "label": "โรงเรียนวัดแหลมเขาจันทร์ (รัฐประชาสามัคคี) จ.ฉะเฉิงเทรา" },
    { "ip": "1.0.168.105", "port": 80, "lat": 14.88051, "lon": 98.79765, "label": "โรงเรียนบ้านห้วยเสือ จ.กาญจนบุรี" },
    { "ip": "182.52.51.215", "port": 80, "lat": 14.59085, "lon": 98.5846, "label": "โรงเรียนบ้านประจำไม้ จ.กาญจนบุรี" },
    { "ip": "182.52.51.224", "port": 80, "lat": 13.124522, "lon": 99.621046, "label": "โรงเรียนบ้านท่าเสลา จ.เพชรบุรี" },
    { "ip": "1.20.140.78", "port": 80, "lat": 17.3023, "lon": 98.1762, "label": "โรงเรียนบ้านแม่อุสุวิทยา จ.ตาก" },
    { "ip": "101.51.121.194", "port": 80, "lat": 16.793021, "lon": 99.030441, "label": "โรงเรียนบ้านลานสาง จ.ตาก" },
    { "ip": "125.26.22.53", "port": 80, "lat": 16.4752, "lon": 98.8404, "label": "โรงเรียนบ้านร่มเกล้า 2 จ.ตาก" },
    { "ip": "182.52.51.220", "port": 80, "lat": 12.529776, "lon": 99.548427, "label": "โรงเรียนอานันท์ จ.ประจวบคีรีขันธ์" },
    { "ip": "182.52.51.239", "port": 80, "lat": 12.137625, "lon": 99.914821, "label": "โรงเรียนบ้านดอนบ่อกุ่ม จ.ประจวบคีรีขันธ์" },
    { "ip": "182.52.51.245", "port": 80, "lat": 11.588597, "lon": 99.625098, "label": "โรงเรียนบ้านไร่ใน จ.ประจวบคีรีขันธ์" },
    { "ip": "118.172.47.92", "port": 81, "lat": 10.4244, "lon": 98.7909, "label": "โรงเรียนบ้านน้ำจืดน้อย จ.ระนอง" },
    { "ip": "118.172.47.91", "port": 80, "lat": 9.57534, "lon": 98.70519, "label": "โรงเรียนบ้านนา จ.ระนอง" },
    { "ip": "101.109.255.196", "port": 80, "lat": 9.051613, "lon": 99.099501, "label": "โรงเรียนบ้านท่าม่วง จ.สุราษฎ์ธานี" },
    { "ip": "101.109.255.204", "port": 80, "lat": 8.52041, "lon": 98.35638, "label": "โรงเรียนนิคมสร้างตนเอง 1 จ.พังงา" },
    { "ip": "1.0.203.225", "port": 80, "lat": 8.17664, "lon": 98.78512, "label": "โรงเรียนบ้านคลองทรายประชาอุทิศ จ.กระบี่" },
    { "ip": "101.109.255.222", "port": 80, "lat": 9.3056, "lon": 98.404, "label": "โรงเรียนบ้านสวนใหม่ จ.พังงา" }
]


# ---------- ฟังก์ชันเช็คสถานะ ----------
def check_ip_port(ip, port, timeout=2):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except:
        return False


def scan_target(target):
    ip = target["ip"]
    port = target["port"]
    status = "ONLINE" if check_ip_port(ip, port) else "OFFLINE"
    return {
        "IP": ip,
        "Port": port,
        "Status": status,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Lat": target.get("lat", None),
        "Lon": target.get("lon", None),
        "Label": target.get("label", "")
    }

# ---------- ส่วนหัว + รูปซ้ายคลิกขยาย ----------
image_path = "1.jpg"
with open(image_path, "rb") as f:
    img_data = base64.b64encode(f.read()).decode("utf-8")

st.markdown(
    f"""
<style>
.top-wrapper {{
    display: flex;
    justify-content: center;
    align-items: center;
    flex-wrap: wrap;
    gap: 40px;
    margin-top: 20px;
    margin-bottom: 30px;
}}
.poster-col img {{
    width: 420px;
    border-radius: 12px;
    cursor: pointer;
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    transition: transform 0.25s ease;
}}
.poster-col img:hover {{
    transform: scale(1.25);
}}
.text-col {{
    max-width: 650px;
    text-align: center;
}}
.text-col h1 {{
    font-size: 40px;          /* ปรับได้ตามชอบ */
    margin: 0 0 10px 0;
    white-space: nowrap;      /* ✅ บังคับไม่ให้ตัดบรรทัด */
}}
/* ให้ตัดบรรทัดได้บนจอเล็ก ไม่งั้นจะล้น */
@media (max-width: 900px) {{
    .text-col h1 {{
        font-size: 26px;
        white-space: normal;
    }}
}}
#overlay {{
    position: fixed;
    display: none;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0,0,0,0.85);
    z-index: 9999;
    justify-content: center;
    align-items: center;
}}
#overlay img {{
    max-width: 90%;
    max-height: 90%;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
}}
</style>

<div class="top-wrapper">
    <div class="poster-col">
        <img src="data:image/jpeg;base64,{img_data}" onclick="openOverlay(this.src)">
    </div>
    <div class="text-col">
        <h1>🚨 เครื่องวัดคลื่นสั่นสะเทือนพื้นดิน 🚨</h1>
        <p style="font-size:16px;">
            🧳 กรมทรัพยากรธรณี 75/10 ถนนพระราม 6 เขตดุสิต กรุงเทพฯ 10400 &nbsp;&nbsp;📞 0 2621 9802<br>
            ⚡ อัปเดตสถานะแบบ Realtime ⚡ &nbsp;&nbsp; 🌐 แผนที่ 🌐
        </p>
    </div>
</div>

<div id="overlay" onclick="closeOverlay()">
    <img id="overlay-img" src="">
</div>

<script>
function openOverlay(src) {{
    const overlay = document.getElementById("overlay");
    const img = document.getElementById("overlay-img");
    img.src = src;
    overlay.style.display = "flex";
}}
function closeOverlay() {{
    document.getElementById("overlay").style.display = "none";
}}
</script>
""",
    unsafe_allow_html=True,
)

# ---------- โหลดครั้งแรก ----------
if "scan_df" not in st.session_state:
    with st.spinner("🐳🐥🐷 ...กำลังโหลดข้อมูลล่าสุด... 🐕‍🦺🐢🐫"):
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(scan_target, targets_combined))
        st.session_state["scan_df"] = pd.DataFrame(results)
        st.session_state["last_scan_time"] = time.time()
        st.success("✅ โหลดข้อมูลสำเร็จ ✅")

# ---------- Auto refresh / ปุ่ม manual ----------
# 20000 ms = 20 วินาที
refresh_count = st_autorefresh(interval=20000, key="auto_refresh", limit=None)
st.write("🔁 Refresh :", refresh_count)

manual_trigger = st.button("👉🏼👉🏼 กดเพื่ออัปเดตสถานะล่าสุด 👈🏼👈🏼", key="manual_update_button")

now = time.time()
last_scan_time = st.session_state.get("last_scan_time", 0)

# เงื่อนไขสแกนใหม่
if manual_trigger or (now - last_scan_time >= 600):
    previous_df = st.session_state.get("scan_df", pd.DataFrame())
    with st.spinner("🔄 กำลังสแกนสถานะเครื่องมือ..."):
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(scan_target, targets_combined))
        current_df = pd.DataFrame(results)
    st.session_state["scan_df"] = current_df
    st.session_state["last_scan_time"] = now
    save_to_history(current_df)

    # แสดง diff สถานะ
    if not previous_df.empty:
        merged_df = pd.merge(previous_df, current_df, on="IP", suffixes=("_ก่อน", "_ล่าสุด"))
        changed = merged_df[merged_df["Status_ก่อน"] != merged_df["Status_ล่าสุด"]]
        if not changed.empty:
            st.warning("🌀 มีการเปลี่ยนแปลงสถานะจากรอบก่อนหน้า:")
            for row in changed.itertuples():
                st.markdown(
                    f"""
                    🔁 <b>{row.Label_ล่าสุด}</b><br>
                    เดิม: <span style="color: {'green' if row.Status_ก่อน == 'ONLINE' else 'red'}">{row.Status_ก่อน}</span> ➡️
                    ปัจจุบัน: <span style="color: {'green' if row.Status_ล่าสุด == 'ONLINE' else 'red'}">{row.Status_ล่าสุด}</span>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ ไม่มีการเปลี่ยนแปลงสถานะจากรอบก่อนหน้า")


# ---------- แสดงผลหลัก ----------
if "scan_df" in st.session_state:
    df = st.session_state["scan_df"].copy()

    # แปลงเวลา + โซนเวลา
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    if df["Timestamp"].dt.tz is None:
        df["Timestamp"] = df["Timestamp"].dt.tz_localize("UTC")
    df["Timestamp"] = df["Timestamp"].dt.tz_convert("Asia/Bangkok")

    last_time = df["Timestamp"].max()
    online_count = (df["Status"] == "ONLINE").sum()
    offline_count = (df["Status"] == "OFFLINE").sum()

    # แถบสรุป
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;background-color:#0e2b47;padding:10px 20px;border-radius:8px;color:white;">
            <div>🕗 ตรวจสอบล่าสุด: {last_time.strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div style="background-color:#f9f9f9;padding:6px 12px;border-radius:6px;">
                <span style="color:green;font-weight:bold;">🟢 ONLINE: {online_count}</span>&nbsp;&nbsp;
                <span style="color:red;font-weight:bold;">🔴 OFFLINE: {offline_count}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,)
 
    # ✅ สร้าง Tabs แยกหน้าจอ
    tabs = st.tabs(["📊 ประวัติ"])
    tab_main = tabs[0]
    with tab_main: # เปลี่ยนกลับเป็น tab2 หรือตามที่คุณตั้งไว้
      st.subheader("🕒 บันทึกประวัติการสลับสถานะ")
    
    # ... โค้ดส่วนดึงข้อมูล ...
change_log = get_status_changes()

if change_log is not None and not change_log.empty:
    # ✅ เพิ่ม .head(10) เพื่อเลือกแสดงเฉพาะ 10 รายการล่าสุด
    # คุณสามารถเปลี่ยนเลข 10 เป็นจำนวนที่ต้องการได้ เช่น 5 หรือ 15
    view_df = change_log[['Timestamp', 'Label', 'Event', 'Current_Status']].head(10)

    # ฟังก์ชันกำหนดสี (ONLINE=เขียว, OFFLINE=แดง)
    def highlight_by_status(row):
        color = 'color: #2ecc71; font-weight: bold;' if row['Current_Status'] == 'ONLINE' else 'color: #e74c3c; font-weight: bold;'
        return [color] * len(row)

    # แสดงตาราง
    st.dataframe(
        view_df.style.apply(highlight_by_status, axis=1),
        column_config={
            "Timestamp": "วัน-เวลา",
            "Label": "ชื่อสถานี",
            "Event": "การเปลี่ยนแปลง",
            "Current_Status": "สถานะปัจจุบัน"
        },
        hide_index=True,
        use_container_width=True,
        # ปรับความสูงตารางให้พอดีกับจำนวนแถว
        height=400 
    )
    st.caption(f"📌 แสดงเฉพาะ 10 รายการล่าสุดที่มีการเปลี่ยนแปลง")
                   
    # แผนที่รวม
    m = folium.Map(location=[13.5, 101], zoom_start=6)
    for row in df.itertuples():
        if pd.isna(row.Lat) or pd.isna(row.Lon):
            continue
        color = "green" if row.Status == "ONLINE" else "red"
        icon_name = "check" if row.Status == "ONLINE" else "times"
        popup_html = f"""
        <b>{row.Label}</b><br>
        <b>Status:</b> <span style='color:{color}'>{row.Status}</span><br>
        <b>เวลาเช็คสถานะล่าสุด:</b> {row.Timestamp.strftime('%Y-%m-%d %H:%M:%S')}
        """
        folium.Marker(
            [row.Lat, row.Lon],
            popup=folium.Popup(popup_html, max_width=500),
            icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
        ).add_to(m)

    # legend
    legend_html = """
    {% macro html(this, kwargs) %}
    <div style='position: fixed; bottom: 50px; left: 50px; width: 220px;
        background-color: white; border: 2px solid grey; z-index:9999;
        font-size:14px; padding: 10px; box-shadow: 2px 2px 6px rgba(0,0,0,0.3);'>
        <b style="color:black;">🗺️ คำอธิบายสัญลักษณ์ 🗺️</b><br>
        <i class="fa fa-check" style="color:green"></i> <span style="color:green;">ONLINE</span><br>
        <i class="fa fa-times" style="color:red"></i> <span style="color:red;">OFFLINE</span>
    </div>
    {% endmacro %}
    """
    legend = MacroElement()
    legend._template = Template(legend_html)
    m.get_root().add_child(legend)

    st_folium(m, use_container_width=True, height=800)

    # ตาราง
    df_display = df[["Label", "Status", "Timestamp", "Lat", "Lon"]].copy()
    df_display.index = df_display.index + 1

    def style_status(val):
        return f"color: {'green' if val == 'ONLINE' else 'red'}"

    st.dataframe(df_display.style.applymap(style_status, subset=["Status"]))

    # ดาวน์โหลด CSV
    csv = df_display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⏬⏬ ดาวน์โหลดตารางสถานะเครื่องมือ ⏬⏬",
        data=csv,
        file_name="สถานะเครื่องวัดคลื่นสั่นสะเทือนพื้นดิน.csv",
        mime="text/csv",
    )

    # เลือกจุดโฟกัสบน Google Map
    selected_label = st.selectbox(
        "⬇️ เลือกสถานที่ติดตั้งเครื่องมือเพื่อดูตำแหน่งใน Google map ⬇️",
        df_display["Label"].tolist(),
    )

    selected_row = df[df["Label"] == selected_label].iloc[0]
    lat = selected_row["Lat"]
    lon = selected_row["Lon"]
    status = selected_row["Status"]
    color = "green" if status == "ONLINE" else "red"

    google_tiles = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"

    m_focus = folium.Map(location=[lat, lon], zoom_start=16, tiles=google_tiles, attr="Google")
    popup_html = f"<b>{selected_row['Label']}</b><br>"
    folium.Marker(
        [lat, lon],
        popup=folium.Popup(popup_html, max_width=500),
        icon=folium.Icon(color=color, icon="info-sign"),
    ).add_to(m_focus)

    st_folium(m_focus, use_container_width=True, height=500)
