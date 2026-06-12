import os
import numpy as np
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point
import shapely.affinity as affinity

# =====================================================================
# 1. PAGE CONFIGURATION & LAYOUT
# =====================================================================
st.set_page_config(
    page_title="UK Wildfire GeoAI Catastrophe Dashboard",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🔥 UK Wildfire GeoAI Catastrophe Dashboard")
st.markdown("""
This dashboard monitors historical wildfire distribution alongside critical infrastructure and national road networks. 
Adjust the real-time weather controls in the sidebar to simulate dynamic, wind-driven hazard propagation plumes.
""")

# =====================================================================
# 2. CACHED DATA LOADING (Reads from Local Snapshot Files)
# =====================================================================
@st.cache_data(show_spinner="Loading data snapshots...")
def load_dashboard_data():
    # Define relative paths matching your data folder setup
    csv_path = os.path.join("data", "wildfire_data.csv")
    infra_path = os.path.join("data", "infrastructure_assets.geojson")
    roads_path = os.path.join("data", "uk_roads.geojson")
    
    # Load Wildfire CSV
    df_wildfires = pd.read_csv(csv_path)
    
    # Load Infrastructure Assets (GeoJSON)
    gdf_infra = gpd.read_file(infra_path)
    
    # Load UK Road Networks (GeoJSON)
    gdf_roads = gpd.read_file(roads_path)
    
    return df_wildfires, gdf_infra, gdf_roads

try:
    df_fires, gdf_assets, gdf_roads = load_dashboard_data()
except Exception as e:
    st.error(f"❌ Error loading data files. Please ensure the 'data' folder contains your exported snapshots. Detailed error: {e}")
    st.stop()

# =====================================================================
# 3. SIDEBAR CONTROLS & WEATHER SIMULATION
# =====================================================================
st.sidebar.header("🌪️ Real-Time Weather Conditions")
st.sidebar.markdown("Simulate wind effects on wildfire exposure boundaries.")

# Wind speed slider (km/h)
wind_speed = st.sidebar.slider(
    "Wind Speed (km/h)", 
    min_value=0, 
    max_value=120, 
    value=25, 
    step=5,
    help="Higher speeds elongate and push the threat plume further downwind."
)

# Wind direction slider (0° = North, 90° = East, etc.)
wind_direction = st.sidebar.slider(
    "Wind Direction (Degrees From)", 
    min_value=0, 
    max_value=360, 
    value=225, # Default Southwest wind common in the UK
    step=5,
    help="The compass direction the wind is BLOWING FROM."
)

# Calculate cardinal direction text for UI clarity
cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
current_direction = cardinals[int((wind_direction + 22.5) % 360 / 45)]
st.sidebar.info(f"💨 Wind Vector: Blowing **FROM** the **{current_direction}** ({wind_direction}°)")

# Sidebar metrics overview
st.sidebar.divider()
st.sidebar.header("📊 Asset Inventories")
st.sidebar.metric("Tracked Wildfire Incidents", len(df_fires))
st.sidebar.metric("Critical Infrastructure Assets", len(gdf_assets))
st.sidebar.metric("Road Segments Cached", len(gdf_roads))

# =====================================================================
# 4. ANISOTROPIC PLUME GEOMETRY CALCULATION
# =====================================================================
def calculate_wind_plumes(df, speed, direction):
    """
    Computes spatial ellipses tracking downwind threat vectors.
    Uses EPSG:27700 (British National Grid) for metric spatial transformations.
    """
    # Create an active Point GeoDataFrame from standard coordinates
    # Automatically handles common naming conventions for latitude/longitude
    lon_col = 'longitude' if 'longitude' in df.columns else 'lon'
    lat_col = 'latitude' if 'latitude' in df.columns else 'lat'
    
    gdf_points = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
        crs="EPSG:4326"
    )
    
    # Project to British National Grid (meters) for accurate spatial projections
    gdf_projected = gdf_points.to_crs(epsg=27700)
    
    base_radius = 400  # Baseline safety perimeter in meters
    stretch = 1.0 + (speed * 0.04)  # Elongation coefficient based on velocity
    shift = speed * 15  # Downwind physical translation distance
    
    # Convert meteorological wind orientation to mathematical geometry angle
    math_angle = (360 - direction + 180) % 360
    
    plume_geometries = []
    for geom in gdf_projected.geometry:
        # 1. Create baseline circular footprint
        circle = Point(geom.x, geom.y).buffer(base_radius)
        # 2. Scale along the axis to mimic propagation patterns
        ellipse = affinity.scale(circle, xfact=1.0, yfact=stretch, origin=(geom.x, geom.y))
        # 3. Shift footprint downwind relative to ignition epicenters
        shifted = affinity.translate(ellipse, xoff=0, yoff=shift)
        # 4. Rotate footprint to align with compass vector paths
        rotated = affinity.rotate(shifted, math_angle, origin=(geom.x, geom.y))
        plume_geometries.append(rotated)
        
    gdf_plumes = gdf_projected.copy()
    gdf_plumes['geometry'] = plume_geometries
    
    # Re-project to global engine coordinates for map ecosystem integration
    return gdf_plumes.to_crs(epsg=4326)

# Execute geometry math reactively based on UI state variables
gdf_threat_plumes = calculate_wind_plumes(df_fires, wind_speed, wind_direction)

# =====================================================================
# 5. GEOSPATIAL MAP RENDERING (Folium Interface Engine)
# =====================================================================
col1, col2 = st.columns([4, 1])

with col1:
    st.subheader("🗺️ Spatial Risk Matrix View")
    
    # Center map display dynamically around median dataset coordinates
    avg_lat = df_fires['latitude'].median() if 'latitude' in df_fires.columns else 54.5
    avg_lon = df_fires['longitude'].median() if 'longitude' in df_fires.columns else -2.5
    
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=6, tiles="cartodbpositron")
    
    # LAYER 1: Dynamic Downwind Hazard Plumes (Rendered underneath for visual stacking)
    folium.GeoJson(
        gdf_threat_plumes,
        name="Wind Hazard Exposure Zones",
        style_function=lambda x: {
            'fillColor': '#ff3333',
            'color': '#cc0000',
            'weight': 1,
            'fillOpacity': 0.20
        },
        tooltip=folium.GeoJsonTooltip(fields=df_fires.columns.tolist()[:3], aliases=df_fires.columns.tolist()[:3])
    ).add_to(m)
    
    # LAYER 2: National Road Networks
    folium.GeoJson(
        gdf_roads,
        name="UK Transportation Network",
        style_function=lambda x: {
            'color': '#555555',
            'weight': 1.2,
            'opacity': 0.6
        }
    ).add_to(m)
    
    # LAYER 3: Critical Infrastructure Assets
    folium.GeoJson(
        gdf_assets,
        name="Critical Infrastructure Assets",
        style_function=lambda x: {
            'fillColor': '#0066cc',
            'color': '#004c99',
            'weight': 1,
            'fillOpacity': 0.7
        },
        marker=folium.CircleMarker(radius=4)
    ).add_to(m)
    
    # LAYER 4: Wildfire Incident Points (The Core Epicenters)
    for idx, row in df_fires.iterrows():
        lon = row['longitude'] if 'longitude' in df_fires.columns else row['lon']
        lat = row['latitude'] if 'latitude' in df_fires.columns else row['lat']
        
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            color='#b30000',
            fill=True,
            fill_color='#ff6666',
            fill_opacity=0.9,
            popup=f"🔥 Wildfire Incident ID: {idx}"
        ).add_to(m)
        
    # Layer control panel widget
    folium.LayerControl(collapsed=False).add_to(m)
    
    # Draw map onto Streamlit frame view
    st_folium(m, width="100%", height=650, returned_objects=[])

with col2:
    st.subheader("💡 Analysis")
    st.markdown("""
    **Layer Interaction Guide:**
    * **Red Ellipses:** Represent dynamic exposure vectors. Move sliders to verify which roads or utility components are intercepted by the wind footprint.
    * **Blue Dots:** Registered local structures and infrastructure nodes.
    * **Grey Vectors:** National connectivity roads available for route or isolation context.
    """)
    st.warning("⚠️ High wind velocities significantly alter shape footprint vectors, tracking downstream geographic components.")