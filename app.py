import os
import sys
import time
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components  # <-- Add this explicit import
from sqlalchemy import create_engine
import pandas as pd
import geopandas as gpd
import numpy as np
import folium
from shapely.geometry import Point, LineString, Polygon
import shapely.affinity as affinity

# =====================================================================
# 0. WINDOWS PYPROJ ENVIRONMENT CONTEXT LOCK
# =====================================================================
PROJ_TARGET_DIR = r"C:\Users\D S PAWAR\miniconda3\envs\geoai_bigdata_env\Library\share\proj"
os.environ["PROJ_DATA"] = PROJ_TARGET_DIR
os.environ["PROJ_LIB"] = PROJ_TARGET_DIR

import pyproj
try:
    pyproj.datadir.set_data_dir(PROJ_TARGET_DIR)
except Exception:
    pass

# Initialize Streamlit application layout configuration
st.set_page_config(page_title="UK Wildfire Predictive GeoAI Dashboard", layout="wide")

# =====================================================================
# 1. DATABASE CONNECTION & CACHED DATA FETCHING
# =====================================================================
RAW_PASSWORD = "anita-geoai"  # Update with your actual PostGIS password
encoded_password = urllib.parse.quote_plus(RAW_PASSWORD)

@st.cache_resource
def get_db_engine():
    return create_engine(f"postgresql://postgres:{encoded_password}@127.0.0.1:5433/uk_cat_model")

engine = get_db_engine()

@st.cache_data
def load_spatial_data(query, geom_col):
    return gpd.read_postgis(query, con=engine, geom_col=geom_col)

# =====================================================================
# 2. DASHBOARD SIDEBAR CONTROLS (GEOAI PREDICTIVE INPUTS)
# =====================================================================
st.sidebar.title("🔥 GeoAI Predictive Controls")
st.sidebar.markdown("Adjust meteorological simulation vectors to calculate fire spread perimeters dynamically.")

# Weather Simulation Vectors
wind_dir = st.sidebar.slider("🌬️ Wind Direction (Bearing Angle °)", 0, 360, 225, step=5, 
                             help="Angle from which the wind blows. 225° represents a South-Westerly wind.")
wind_speed = st.sidebar.slider("💨 Wind Speed (km/h)", 5, 80, 35, step=5)
frp_threshold = st.sidebar.slider("⚡ Minimum Fire Intensity (FRP)", 0.0, 50.0, 5.0, step=1.0)

st.sidebar.subheader("🗺️ Dynamic Layers")
show_spread_vectors = st.sidebar.checkbox("Show Predicted Spread Footprints", value=True)
show_high_risk_assets = st.sidebar.checkbox("Highlight Vulnerable Buildings", value=True)

# =====================================================================
# 3. SPATIAL DATA INGEST
# =====================================================================
fires_query = "SELECT frp, geom_4326 FROM uk_wildfires;"
gdf_fires = load_spatial_data(fires_query, "geom_4326")
filtered_fires = gdf_fires[gdf_fires['frp'] >= frp_threshold].copy()

# =====================================================================
# 4. GEOAI SPREAD PREDICTION ENGINE (ELLIPTICAL PLUME SIMULATION)
# =====================================================================
predicted_plumes_4326 = gpd.GeoDataFrame()

if not filtered_fires.empty:
    fires_27700 = filtered_fires.to_crs("EPSG:27700")
    plume_geometries = []
    
    # Calculate fire spread geometry based on weather metrics
    for _, row in fires_27700.iterrows():
        # FIX: Explicitly index the database-named column inside the loop
        origin = row['geom_4326']  
        frp = row['frp']
        
        # Base fire radius scaling with energy output (meters)
        base_radius = 1500 + (frp * 50)
        
        # Elongation factor determined directly by wind speeds
        length_factor = 1.0 + (wind_speed / 20.0)
        width_factor = 1.0
        
        # Create an initial unrotated baseline ellipse at origin coordinates
        ellipse = origin.buffer(base_radius)
        ellipse = affinity.scale(ellipse, xfact=width_factor, yfact=length_factor, origin=origin)
        
        # Translate the center of mass downwind so the ignition source sits at the upwind edge
        displacement_distance = (base_radius * length_factor) - base_radius
        math_angle = np.radians(90 - wind_dir)
        dx = displacement_distance * np.cos(math_angle)
        dy = displacement_distance * np.sin(math_angle)
        ellipse = affinity.translate(ellipse, xoff=dx, yoff=dy)
        
        # Rotate the final plume boundary alignment to face downwind direction
        ellipse = affinity.rotate(ellipse, angle=180-wind_dir, origin=origin)
        plume_geometries.append(ellipse)
        
    fires_27700['geom_4326'] = plume_geometries
    fires_27700 = fires_27700.set_geometry('geom_4326')
    predicted_plumes_4326 = fires_27700.to_crs("EPSG:4326")

# =====================================================================
# 5. ASSET VULNERABILITY SCORE ENGINE (SPATIAL JOIN)
# =====================================================================
st.title("🇬🇧 UK Catastrophe Risk & Fire Spread Dashboard")

scored_buildings_4326 = gpd.GeoDataFrame()

if show_high_risk_assets and not predicted_plumes_4326.empty:
    with st.spinner("Executing spatial analysis on industrial footprints..."):
        # Load asset footprint polygon tables from database
        gdf_buildings = load_spatial_data("SELECT osm_id, name, building_type, geom_4326 FROM uk_buildings;", "geom_4326")
        
        if not gdf_buildings.empty:
            # Transform to metric coordinates to ensure highly accurate spatial distance indexing
            buildings_27700 = gdf_buildings.to_crs("EPSG:27700")
            plumes_27700 = predicted_plumes_4326.to_crs("EPSG:27700")
            
            # Map type weights to building classifications
            type_weights = {'industrial': 1.5, 'commercial': 1.2, 'warehouse': 1.0}
            buildings_27700['weight'] = buildings_27700['building_type'].map(type_weights).fillna(1.0)
            
            # Perform intersection calculation to find structures inside the predicted path
            intersected = gpd.sjoin(buildings_27700, plumes_27700, how="inner", predicate="intersects")
            
            # Assign Vulnerability Index Scores based on structural properties and intensity
            if not intersected.empty:
                intersected['vulnerability_score'] = (100.0 * intersected['weight'] * (intersected['frp'] / 10.0)).clip(45.0, 100.0)
                scored_buildings_4326 = intersected.to_crs("EPSG:4326")

# =====================================================================
# 6. APP RENDERING AND MAP CREATION
# =====================================================================
kpi1, kpi2 = st.columns(2)
kpi1.metric("Active Tracked Hazards", len(filtered_fires))
kpi2.metric("Buildings in Predicted Path", len(scored_buildings_4326) if not scored_buildings_4326.empty else 0)

m = folium.Map(location=[54.0, -2.5], zoom_start=6, tiles="CartoDB dark_matter")

# Draw Plumes
if show_spread_vectors and not predicted_plumes_4326.empty:
    folium.GeoJson(
        predicted_plumes_4326,
        style_function=lambda x: {'fillColor': '#e65c00', 'color': '#ff9900', 'weight': 1.5, 'fillOpacity': 0.25},
        name="Predicted Spread Vectors"
    ).add_to(m)

# Draw Scored Asset Footprints
if show_high_risk_assets and not scored_buildings_4326.empty:
    for _, row in scored_buildings_4326.iterrows():
        v_score = int(row['vulnerability_score'])
        color_hex = "#d32f2f" if v_score > 75 else "#f57c00"
        
        popup_html = f"""
        🏢 <b>Asset:</b> {row['name']}<br>
        ⚙️ <b>Type:</b> {row['building_type']}<br>
        🚨 <b>Vulnerability Score:</b> <span style='color:{color_hex};font-weight:bold;'>{v_score}/100</span>
        """
        
        folium.GeoJson(
            row['geom_4326'], # FIX: Target explicit column key for buildings layer
            style_function=lambda x, ch=color_hex: {'fillColor': ch, 'color': ch, 'weight': 1, 'fillOpacity': 0.7},
            popup=folium.Popup(popup_html, max_width=250)
        ).add_to(m)

# Draw Central Ignition Points using verified schema columns
for _, row in filtered_fires.iterrows():
    popup_text = f"🔥 <b>Fire Hotspot</b><br>⚡ <b>FRP Intensity:</b> {row['frp']}"
    folium.CircleMarker(
        location=[row['geom_4326'].y, row['geom_4326'].x], # Explicit column key
        radius=5, 
        color='#ffffff', 
        fill=True, 
        fill_color='#ff1a1a', 
        fill_opacity=0.9,
        popup=folium.Popup(popup_text, max_width=200)
    ).add_to(m)

# Render Map
st.subheader("🌐 Spatial Simulation & Risk Forecast")
components.html(m._repr_html_(), height=600)  # <-- Changed from st.components.html to components.html

# Render Asset Inspection Ledger Dataframe
if not scored_buildings_4326.empty:
    st.subheader("📊 Vulnerable Structural Asset Register")
    display_df = pd.DataFrame(scored_buildings_4326[['osm_id', 'name', 'building_type', 'vulnerability_score']])
    st.dataframe(display_df.sort_values(by='vulnerability_score', ascending=False), use_container_width=True)