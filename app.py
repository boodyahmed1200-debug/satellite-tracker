import streamlit as st
import pandas as pd
import time
import datetime
import os
import math
import urllib.request
import io  # عشان نقرأ البيانات النصية
from skyfield.api import load, wgs84

# ---------------------------------------------------------
# 1. بيانات الطوارئ (Fallback Data)
# عشان لو النت فصل، الموقع يفضل شغال ببيانات مخزنة
# ---------------------------------------------------------
FALLBACK_TLE_DATA = """
ISS (ZARYA)
1 25544U 98067A   23335.44285481  .00012930  00000+0  23436-3 0  9999
2 25544  51.6418 152.8821 0004881 229.7580 201.7785 15.49611897427524
NILESAT 201
1 36830U 10037A   23335.14512311 -.00000243  00000+0  00000+0 0  9993
2 36830   0.0261 245.8421 0002077 341.4455 309.6932  1.00270302 48128
BADR-4
1 29279U 06032A   23335.51698016 -.00000261  00000+0  00000+0 0  9990
2 29279   0.0427 210.4502 0003373 305.6045 147.3043  1.00271855 62510
TIANGONG
1 48274U 21035A   23335.41783012  .00031860  00000+0  38601-3 0  9993
2 48274  41.4736 351.4123 0003833 270.9590 139.2779 15.60037903145272
NAVSTAR 80 (USA 309)
1 46826U 20078A   23335.26801389 -.00000053  00000+0  00000+0 0  9996
2 46826  55.2640 160.9977 0009915 269.6902  90.2285  2.00555664 22016
HUBBLE
1 20580U 90037B   23334.83968157  .00001820  00000+0  72385-4 0  9996
2 20580  28.4695 107.3704 0002663 311.0111 142.1867 15.09305242612280
STARLINK-1008
1 44714U 19074B   23335.23456789  .00012345  00000+0  12345-3 0  9999
2 44714  53.0547 175.3002 0001234  90.1234 270.1234 15.06399672 12345
"""

# ---------------------------------------------------------
# 2. إعدادات الصفحة
# ---------------------------------------------------------
st.set_page_config(page_title="Satellite Command Center 🛰️", layout="wide", page_icon="📡")

st.markdown("""
<style>
    [data-testid="stMetricValue"] {font-size: 22px; font-weight: bold;}
    thead tr th:first-child {display:none}
    tbody th {display:none}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 3. القائمة الجانبية
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
# 4. دوال مساعدة
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
# 5. تحميل البيانات (النظام الذكي Smart Loader)
# ---------------------------------------------------------
@st.cache_resource
def load_data():
    ts = load.timescale()
    local_filename = '/tmp/active_sats.txt'
    url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    sats = []
    
    # المحاولة الأولى: التحميل من النت
    try:
        if not os.path.exists(local_filename):
            # بنحط timeout عشان لو طول يفصل بسرعة ويروح للخطة البديلة
            with urllib.request.urlopen(url, timeout=5) as response:
                content = response.read()
                with open(local_filename, 'wb') as f:
                    f.write(content)
        
        sats = load.tle_file(local_filename)
        st.sidebar.success("✅ Data Source: Live Network")
        
    except Exception as e:
        # لو حصل أي خطأ (نت فاصل، سيرفر واقع)، شغل نظام الطوارئ
        st.sidebar.warning(f"⚠️ Network Error: {e}")
        st.sidebar.info("🔄 Switching to Offline Backup Mode...")
        
        # تحميل البيانات من المتغير اللي فوق (FALLBACK_TLE_DATA)
        # بنحول النص لملف وهمي في الذاكرة عشان المكتبة تقرأه
        f_obj = io.BytesIO(FALLBACK_TLE_DATA.encode('utf-8'))
        sats = load.tle_file(f_obj)
        
    return ts, sats

ts, all_satellites = load_data()

if not all_satellites:
    st.error("❌ Critical Error: Could not load satellite data.")
    st.stop()

# تكوين الفريق
target_names = ['ISS (ZARYA)', 'NILESAT 201', 'BADR-4', 'TIANGONG', 'NAVSTAR 80', 'HUBBLE', 'STARLINK']
my_fleet = []

# تصفية الأقمار (إما بالاسم أو النوع)
for name in target_names:
    for sat in all_satellites:
        if name in sat.name:
            # بنمنع التكرار
            if not any(sat.name == s.name for s in my_fleet):
                my_fleet.append(sat)
            # لو ستارلينك، كفاية 5 بس
            if 'STARLINK' in name and len([s for s in my_fleet if 'STARLINK' in s.name]) >= 5:
                break
            if 'STARLINK' not in name: # للأقمار الوحيدة زي نايل سات، خد واحد بس واخرج
                break

# ---------------------------------------------------------
# 6. ميزة التنبؤ
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("🔮 Next 24h Passes")

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
    st.sidebar.warning("System Initializing...")

# ---------------------------------------------------------
# 7. العرض الحي
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
