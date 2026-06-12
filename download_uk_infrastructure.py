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

import geopandas as gpd
import requests
from shapely.geometry import LineString, Polygon
from sqlalchemy import create_engine, text

# =====================================================================
# 1. DATABASE CONFIGURATION
# =====================================================================
RAW_PASSWORD = "anita-geoai"  # Update with your real password

encoded_password = urllib.parse.quote_plus(RAW_PASSWORD)
USERNAME = "postgres"
HOST = "127.0.0.1"  
PORT = "5433"       
DATABASE = "uk_cat_model"

connection_string = f"postgresql://{USERNAME}:{encoded_password}@{HOST}:{PORT}/{DATABASE}"
engine = create_engine(connection_string)

# =====================================================================
# 2. DYNAMICALLY TARGET THE HIGHEST INTENSITY HAZARD ZONE
# =====================================================================
print("🔍 Querying database to locate active wildfire hotspots...")
try:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT ST_Y(geom_4326) as lat, ST_X(geom_4326) as lon, frp 
            FROM uk_wildfires 
            ORDER BY frp DESC 
            LIMIT 1;
        """)).fetchone()
except Exception as e:
    print("❌ Could not read from uk_wildfires table. Ensure data exists.")
    raise e

if result and result[0] is not None:
    fire_lat, fire_lon, fire_frp = result
    print(f"🔥 Found highest intensity hotspot (FRP: {fire_frp}) at Lat: {fire_lat}, Lon: {fire_lon}")
    
    # Generate a tight bounding box (~15-20km buffer zone) centered on the fire
    bbox = f"{fire_lat - 0.1},{fire_lon - 0.15},{fire_lat + 0.1},{fire_lon + 0.15}"
    print(f"📍 Generated target bounding box: {bbox}")
else:
    print("⚠️ No fires found in table. Defaulting to Sussex fallback region...")
    bbox = "50.85,-0.15,50.95,-0.08"

# =====================================================================
# 3. FIREWALL-SAFE OVERPASS QUERY
# =====================================================================
overpass_url = "https://overpass-api.de/api/interpreter"
overpass_query = f"""
[out:json][timeout:120];
(
  way["building"="commercial"]({bbox});
  way["building"="industrial"]({bbox});
  way["building"="warehouse"]({bbox});
  way["highway"="motorway"]({bbox});
  way["highway"="trunk"]({bbox});
  way["highway"="primary"]({bbox});
  way["highway"="secondary"]({bbox});
  way["highway"="tertiary"]({bbox});
);
out body;
>;
out skel qt;
"""

headers = {
    "User-Agent": "GeoAILabCatModel/1.0 (Spatial Database Lab Project)",
    "Content-Type": "application/x-www-form-urlencoded"
}

# =====================================================================
# 4. DATA DOWNLOAD
# =====================================================================
print("🌐 Requesting exposed infrastructure from OpenStreetMap Overpass API...")
response = requests.post(overpass_url, data={"data": overpass_query}, headers=headers)

if response.status_code != 200:
    print(f"❌ Server returned error code {response.status_code}")
    exit()

data = response.json()
print("✅ JSON payload successfully fetched.")

# =====================================================================
# 5. GEOSPATIAL VECTOR PARSING
# =====================================================================
nodes = {el["id"]: (el["lon"], el["lat"]) for el in data["elements"] if el["type"] == "node"}
buildings_list = []
roads_list = []

for el in data["elements"]:
    if el["type"] == "way" and "nodes" in el:
        coordinate_pairs = [nodes[node_id] for node_id in el["nodes"] if node_id in nodes]
        if len(coordinate_pairs) < 2:
            continue
        
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        
        if "building" in tags and len(coordinate_pairs) >= 3:
            poly = Polygon(coordinate_pairs)
            buildings_list.append({
                "osm_id": el["id"], "name": name, 
                "building_type": tags.get("building"), "geometry": poly
            })
        elif "highway" in tags:
            line = LineString(coordinate_pairs)
            roads_list.append({
                "osm_id": el["id"], "name": name, 
                "road_type": tags.get("highway"), "geometry": line
            })

# =====================================================================
# 6. POSTGIS INGESTION (WIPING PREVIOUS REGION OUT)
# =====================================================================
# We use 'replace' to ensure old, non-intersecting layers are cleared out
if buildings_list:
    gdf_buildings = gpd.GeoDataFrame(buildings_list, crs="EPSG:4326")
    print(f"📥 Streaming {len(gdf_buildings)} structural shapes to staging...")
    gdf_buildings.to_postgis("uk_buildings_staging", con=engine, if_exists="replace", index=False)
    
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE uk_buildings;"))  # Clear old data
        conn.execute(text("""
            INSERT INTO uk_buildings (osm_id, name, building_type, geom_4326, geom_27700)
            SELECT osm_id, name, building_type, geometry, ST_Transform(geometry, 27700)
            FROM uk_buildings_staging
            ON CONFLICT (osm_id) DO NOTHING;
            DROP TABLE IF EXISTS uk_buildings_staging;
        """))

if roads_list:
    gdf_roads = gpd.GeoDataFrame(roads_list, crs="EPSG:4326")
    print(f"🛣️ Streaming {len(gdf_roads)} transport elements to staging...")
    gdf_roads.to_postgis("uk_roads_staging", con=engine, if_exists="replace", index=False)
    
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE uk_roads;"))  # Clear old data
        conn.execute(text("""
            INSERT INTO uk_roads (osm_id, name, road_type, geom_4326, geom_27700)
            SELECT osm_id, name, road_type, geometry, ST_Transform(geometry, 27700)
            FROM uk_roads_staging
            ON CONFLICT (osm_id) DO NOTHING;
            DROP TABLE IF EXISTS uk_roads_staging;
        """))

print("\n🎉 SUCCESS! Target hazard area assets are fully synced with active wildfires.")