import streamlit as st
import pandas as pd
import time
import datetime
import os
import math
import urllib.request  # مكتبة التحميل اليدوي
from skyfield.api import load, wgs84

# ---------------------------------------------------------
# 1. إعدادات الصفحة
# ---------------------------------------------------------
st.set_page_config(
    page_title="Satellite Command Center 🛰️",
    layout="wide",
    page_icon="📡",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 22px;
        font-weight: bold;
    }
    thead tr th:first-child {display:none}
    tbody th {display:none}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. القائمة الجانبية
# ---------------------------------------------------------
st.sidebar.title("⚙️ Control Panel")
st.sidebar.subheader("📍 Base Station")
city_options = {
    "Cairo (Egypt)": (30.0444, 31.2357),
    "Mecca (KSA)": (21.3891, 39.8579),
    "London (UK)": (51.5074, -0.1278),
    "New York (USA)": (40.7128, -74.0060),
    "Tokyo (Japan)": (35.6762, 139.6503),
    "Sydney (Australia)": (-33.8688, 151.2093)
}
selected_city = st.sidebar.selectbox("Select Location", list(city_options.keys()))
user_lat, user_long = city_options[selected_city]
my_location = wgs84.latlon(user_lat, user_long)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Force Update TLE Data"):
    st.cache_resource.clear()
    st.rerun()

# ---------------------------------------------------------
# 3. دوال مساعدة
# ---------------------------------------------------------
def get_direction(azimuth_deg):
    dirs = ['N ⬆️', 'NE ↗️', 'E ➡️', 'SE ↘️', 'S ⬇️', 'SW ↙️', 'W ⬅️', 'NW ↖️']
    ix = round(azimuth_deg / 45)
    return dirs[ix % 8]

def calculate_footprint_area(altitude_km):
    if altitude_km <= 0: return 0
    R_earth = 6371000
    h_meters = altitude_km * 1000
    cos_theta = R_earth / (R_earth + h_meters)
    area_m2 = 2 * math.pi * (R_earth**2) * (1 - cos_theta)
    return area_m2

# ---------------------------------------------------------
# 4. تحميل البيانات (النسخة المعدلة للسيرفر)
# ---------------------------------------------------------
@st.cache_resource
def load_data():
    ts = load.timescale()
    
    # الحل السحري: بنحفظ الملف في مجلد /tmp المسموح بالكتابة فيه
    local_filename = '/tmp/active_sats.txt'
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    
    # بنستخدم طريقة تحميل يدوية عشان نتفادى مشاكل Skyfield مع السيرفر
    try:
        # لو الملف مش موجود أو إحنا عايزين نحدثه
        if not os.path.exists(local_filename):
            with urllib.request.urlopen(url) as response:
                content = response.read()
                with open(local_filename, 'wb') as f:
                    f.write(content)
        
        # بنقرأ الملف من المكان الآمن ده
        sats = load.tle_file(local_filename)
        
    except Exception as e:
        st.error(f"Server Error (TLE Download): {e}")
        # حل احتياطي لو النت فصل: رجع قائمة فاضية عشان الموقع ميقعش
        sats = []
        
    return ts, sats

ts, all_satellites = load_data()

# لو التحميل فشل، وقف الكود هنا عشان ميعملش Error تاني
if not all_satellites:
    st.stop()

target_names = ['ISS (ZARYA)', 'NILESAT 201', 'BADR-4', 'TIANGONG', 'NAVSTAR 80', 'HUBBLE']
my_fleet = []
for name in target_names:
    for sat in all_satellites:
        if name in sat.name:
            my_fleet.append(sat)
            break
sl_count = 0
for sat in all_satellites:
    if 'STARLINK' in sat.name and sl_count < 5:
        my_fleet.append(sat)
        sl_count += 1

# ---------------------------------------------------------
# 5. ميزة التنبؤ
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("🔮 Next 24h Passes")

# حماية عشان لو القائمة فاضية
if my_fleet:
    prediction_sat_name = st.sidebar.selectbox("Select Satellite", [s.name for s in my_fleet])
    target_sat = next((s for s in my_fleet if s.name == prediction_sat_name), None)

    if st.sidebar.button("Calculate Schedule 📅"):
        st.sidebar.info(f"Computing passes for **{prediction_sat_name}**...")
        t0 = ts.now()
        t1 = ts.from_datetime(t0.utc_datetime() + datetime.timedelta(days=1))
        times, events = target_sat.find_events(my_location, t0, t1, altitude_degrees=10.0)
        
        if len(times) > 0:
            pass_list = []
            for ti, event in zip(times, events):
                event_name = ('🚀 Rise', '☀️ Peak', '📉 Set')[event]
                pass_list.append({"Time": ti.utc_strftime('%H:%M:%S'), "Event": event_name})
            st.sidebar.dataframe(pd.DataFrame(pass_list), hide_index=True)
        else:
            st.sidebar.warning("No visible passes.")
else:
    st.sidebar.warning("Waiting for data...")

# ---------------------------------------------------------
# 6. العرض الحي
# ---------------------------------------------------------
st.title(f"🛰️ Satellite Operations Center | {selected_city}")

placeholder = st.empty()

while True:
    t = ts.now()
    data_list = []
    
    for sat in my_fleet:
        difference = sat - my_location
        topocentric = difference.at(t)
        alt, az, distance = topocentric.altaz()
        
        geocentric = sat.at(t)
        subpoint = geocentric.subpoint()
        height_km = subpoint.elevation.km
        
        v_vector = geocentric.velocity.km_per_s
        speed_kms = math.sqrt(sum(v**2 for v in v_vector))
        area_m2 = calculate_footprint_area(height_km)
        
        is_visible = alt.degrees > 0
        direction_arrow = get_direction(az.degrees)
        
        if height_km < 2000: 
            o_type = "LEO (Internet)"
            color = "#00ff00"
        elif height_km < 35000: 
            o_type = "MEO (GPS)"
            color = "#0000ff"
        else: 
            o_type = "GEO (TV)"
            color = "#ff0000"
            
        status_icon = "🟢 LIVE" if is_visible else "🔻 OFF"
        
        data_list.append({
            "Satellite": sat.name,
            "Status": status_icon,
            "Speed (km/s)": f"{speed_kms:.2f}",
            "Footprint (m²)": f"{area_m2:,.0f}",
            "Compass": direction_arrow,
            "Elevation": f"{alt.degrees:.1f}°",
            "Altitude (km)": f"{height_km:.0f}",
            "Type": o_type,
            "lat": subpoint.latitude.degrees,
            "lon": subpoint.longitude.degrees,
            "size": 200 if is_visible else 30,
            "color": color
        })

    df = pd.DataFrame(data_list)

    with placeholder.container():
        if not df.empty:
            st.map(df, latitude='lat', longitude='lon', size='size', color='color', zoom=1)
            st.markdown("### 📊 Live Telemetry")
            st.dataframe(
                df[["Status", "Satellite", "Speed (km/s)", "Footprint (m²)", "Compass", "Altitude (km)", "Type"]],
                use_container_width=True,
                hide_index=True
            )
        
    time.sleep(1)
