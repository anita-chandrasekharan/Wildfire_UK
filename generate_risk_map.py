import os
import sys
import urllib.parse

# =====================================================================
# 0. PYPROJ WINDOWS ENVIRONMENT PATCH
# =====================================================================
conda_proj_path = os.path.join(sys.prefix, "Library", "share", "proj")
if os.path.exists(conda_proj_path):
    os.environ["PROJ_DATA"] = conda_proj_path
    os.environ["PROJ_LIB"] = conda_proj_path 

import folium
import geopandas as gpd
from sqlalchemy import create_engine

# =====================================================================
# 1. DATABASE CONNECTION
# =====================================================================
RAW_PASSWORD = "anita-geoai"  # Update with your real password

encoded_password = urllib.parse.quote_plus(RAW_PASSWORD)
USERNAME = "postgres"
HOST = "127.0.0.1"  
PORT = "5433"       
DATABASE = "uk_cat_model"

connection_string = f"postgresql://{USERNAME}:{encoded_password}@{HOST}:{PORT}/{DATABASE}"
engine = create_engine(connection_string)

print("⚡ Connecting to PostGIS database and extracting layers...")

# =====================================================================
# 2. LOAD & CLEAN SPATIAL LAYERS DEFENSIVELY
# =====================================================================
# 1. Wildfires
gdf_fires = gpd.read_postgis("SELECT frp, acq_date, geom_4326 FROM uk_wildfires;", con=engine, geom_col="geom_4326")
gdf_fires = gdf_fires.rename_geometry('geometry')
gdf_fires.crs = "EPSG:4326"

# 2. Hazard Buffers
gdf_buffers = gpd.read_postgis("SELECT risk_level, radius_km, geom_4326 FROM uk_hazard_buffers;", con=engine, geom_col="geom_4326")
gdf_buffers = gdf_buffers.rename_geometry('geometry')
gdf_buffers.crs = "EPSG:4326"

# 3. Roads (Clean Nulls for Tooltips)
gdf_roads = gpd.read_postgis("SELECT name, road_type, geom_4326 FROM uk_roads;", con=engine, geom_col="geom_4326")
gdf_roads = gdf_roads.rename_geometry('geometry')
gdf_roads.crs = "EPSG:4326"
gdf_roads['name'] = gdf_roads['name'].fillna('Unnamed Route')
gdf_roads['road_type'] = gdf_roads['road_type'].fillna('Unknown')

# 4. Buildings (Clean Nulls for Tooltips)
gdf_buildings = gpd.read_postgis("SELECT name, building_type, geom_4326 FROM uk_buildings;", con=engine, geom_col="geom_4326")
if not gdf_buildings.empty:
    gdf_buildings = gdf_buildings.rename_geometry('geometry')
    gdf_buildings.crs = "EPSG:4326"
    gdf_buildings['name'] = gdf_buildings['name'].fillna('Unnamed Building')
    gdf_buildings['building_type'] = gdf_buildings['building_type'].fillna('Unknown')

print(f"📊 Extracted Assets Count:")
print(f"   - Active Wildfire Points: {len(gdf_fires)}")
print(f"   - Concentric Buffer Rings: {len(gdf_buffers)}")
print(f"   - Transport Asset Lines: {len(gdf_roads)}")
print(f"   - Structural Footprints: {len(gdf_buildings)}")

# =====================================================================
# 3. MAP CONFIGURATION & CANVAS INITIALIZATION
# =====================================================================
if gdf_fires.empty:
    print("❌ Critical Error: No fire data detected in database. Map cannot center.")
    exit()

# Center dynamically on the coordinates of the fire hotspot
center_lat = gdf_fires['geometry'].y.mean()
center_lon = gdf_fires['geometry'].x.mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB dark_matter")

# =====================================================================
# 4. RENDERING VECTOR OVERLAYS
# =====================================================================

# Color map for the threat tiers
buffer_colors = {
    "High Risk Tier 1": "#d32f2f",      # Crimson
    "Elevated Risk Tier 2": "#f57c00",  # Dark Orange
    "Monitored Risk Tier 3": "#fbc02d"  # Amber Yellow
}

print("🎨 Sketching layered map features...")

# Draw Hazard Buffers
for _, row in gdf_buffers.iterrows():
    risk = row['risk_level']
    color = buffer_colors.get(risk, "#ffffff")
    folium.GeoJson(
        row['geometry'].__geo_interface__,
        style_function=lambda x, c=color: {
            'fillColor': c,
            'color': c,
            'weight': 2,
            'fillOpacity': 0.12
        },
        tooltip=f"<b>{risk}</b><br>Radius Boundary: {row['radius_km']} km"
    ).add_to(m)

# Draw Road Networks
folium.GeoJson(
    gdf_roads.__geo_interface__,
    style_function=lambda x: {
        'color': '#00e5ff',
        'weight': 2.5,
        'opacity': 0.75
    },
    tooltip=folium.GeoJsonTooltip(fields=['name', 'road_type'], aliases=['Road:', 'Type:'])
).add_to(m)

# Draw Building Assets
if not gdf_buildings.empty:
    folium.GeoJson(
        gdf_buildings.__geo_interface__,
        style_function=lambda x: {
            'fillColor': '#e040fb',
            'color': '#ba68c8',
            'weight': 1,
            'fillOpacity': 0.55
        },
        tooltip=folium.GeoJsonTooltip(fields=['name', 'building_type'], aliases=['Building:', 'Use Class:'])
    ).add_to(m)

# Draw Central Heat Points
for _, row in gdf_fires.iterrows():
    folium.CircleMarker(
        location=[row['geometry'].y, row['geometry'].x],
        radius=7,
        color='#ff1744',
        fill=True,
        fill_color='#ff9100',
        fill_opacity=1.0,
        tooltip=f"🔥 <b>Thermal Wildfire Signal</b><br>FRP Intensity: {row['frp']}<br>Observed: {row['acq_date']}"
    ).add_to(m)

# =====================================================================
# 5. GENERATE FILE OUTPUT
# =====================================================================
output_html = "wildfire_risk_map.html"
m.save(output_html)
print(f"\n🎉 SUCCESS! Map file fully rebuilt. Open it here: {output_html}")