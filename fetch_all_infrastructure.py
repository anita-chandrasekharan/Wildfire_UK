import os
import sys
import time
import urllib.parse
import requests
from sqlalchemy import create_engine
import pandas as pd

# =====================================================================
# 0. DEEP PYPROJ ENVIROMENT & DATABASE CONTEXT LOCK
# =====================================================================
# Hardcoded absolute path to your active Conda environment's PROJ share folder
PROJ_TARGET_DIR = r"C:\Users\D S PAWAR\miniconda3\envs\geoai_bigdata_env\Library\share\proj"

# Set system-level environment flags
os.environ["PROJ_DATA"] = PROJ_TARGET_DIR
os.environ["PROJ_LIB"] = PROJ_TARGET_DIR

# Import pyproj directly and force-inject the database directory path
import pyproj
try:
    pyproj.datadir.set_data_dir(PROJ_TARGET_DIR)
except Exception as e:
    print(f"ℹ️ Core patch note: {e}")

# Now safe to import spatial libraries
import geopandas as gpd
from shapely.geometry import LineString, Polygon

# =====================================================================
# 1. DATABASE CONNECTION
# =====================================================================
RAW_PASSWORD = "anita-geoai"  # Update with your database password
encoded_password = urllib.parse.quote_plus(RAW_PASSWORD)

engine = create_engine(f"postgresql://postgres:{encoded_password}@127.0.0.1:5433/uk_cat_model")

print("🔌 Connected to PostGIS. Extracting active land fire coordinates...")

# Fetch the raw dataset
gdf_fires = gpd.read_postgis("SELECT frp, geom_4326 FROM uk_wildfires;", con=engine, geom_col="geom_4326")
print(f"🔥 Found {len(gdf_fires)} raw fire records.")

# =====================================================================
# 2. SPATIAL DISSOLVE (Grouping Overlapping Bounding Boxes)
# =====================================================================
print("⚙️ Optimizing search windows by dissolving overlapping fire zones...")
# Buffer points by ~0.10 degrees (~11km) to capture full hazard areas
buffered_fires = gdf_fires['geom_4326'].buffer(0.10)
unified_zones = buffered_fires.unary_union

# Convert unified shapes into a clean iterable list of geometries
if unified_zones.geom_type == 'Polygon':
    search_regions = [unified_zones]
elif unified_zones.geom_type == 'MultiPolygon':
    search_regions = list(unified_zones.geoms)
else:
    search_regions = []

print(f"💎 Optimization Complete: Consolidated 27 fire points into {len(search_regions)} unique spatial query blocks.")

# Master storage lists
all_roads = []
all_buildings = []

# Headers to satisfy Overpass API requirements and prevent blocks
headers = {
    'User-Agent': 'GeoAICatastropheModel/1.0 (Contact: student@university.ac.uk)',
    'Accept-Encoding': 'gzip, deflate'
}

# =====================================================================
# 3. BATCH FETCH VIA OVERPASS API
# =====================================================================
for idx, region in enumerate(search_regions):
    b_west, b_south, b_east, b_north = region.bounds
    print(f"[{idx + 1}/{len(search_regions)}] Querying consolidated block: SW({b_south:.3f}, {b_west:.3f}) to NE({b_north:.3f}, {b_east:.3f})...")

    overpass_url = "https://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json][timeout:120];
    (
      way["highway"~"motorway|trunk|primary|secondary|tertiary"]({b_south},{b_west},{b_north},{b_east});
      way["building"~"industrial|commercial|warehouse"]({b_south},{b_west},{b_north},{b_east});
    );
    out body;
    >;
    out skel qt;
    """

    try:
        response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers, timeout=60)
        
        if response.status_code == 429:
            print("⚠️ Server rate limit hit (429). Cooling down for 15 seconds...")
            time.sleep(15)
            response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers, timeout=60)
            
        if response.status_code != 200:
            print(f"❌ Server rejected request with Status Code: {response.status_code}. Skipping block.")
            continue
            
        data = response.json()
        elements = data.get('elements', [])
        nodes = {e['id']: (e['lon'], e['lat']) for e in elements if e['type'] == 'node'}

        for e in elements:
            if e['type'] == 'way':
                way_nodes = e.get('nodes', [])
                coords = [nodes[nid] for nid in way_nodes if nid in nodes]
                if len(coords) < 2:
                    continue

                tags = e.get('tags', {})
                osm_id = e['id']

                if 'highway' in tags:
                    all_roads.append({
                        'osm_id': osm_id,
                        'name': tags.get('name', 'Unnamed Route'),
                        'road_type': tags.get('highway'),
                        'geometry': LineString(coords)
                    })
                elif 'building' in tags:
                    if len(coords) >= 3:
                        all_buildings.append({
                            'osm_id': osm_id,
                            'name': tags.get('name', 'Unnamed Building'),
                            'building_type': tags.get('building'),
                            'geometry': Polygon(coords)
                        })

        # Cooldown interval to respect free public tier constraints
        time.sleep(4)

    except Exception as ex:
        print(f"⚠️ Block download skipped due to an error: {ex}")
        continue

# =====================================================================
# 4. DATA COMPILATION AND DB EXPORT
# =====================================================================
print("\n⚙️ Processing final spatial metrics and purging duplicates...")

if all_roads:
    df_r = pd.DataFrame(all_roads).drop_duplicates(subset=['osm_id'])
    gdf_roads = gpd.GeoDataFrame(df_r, geometry='geometry', crs="EPSG:4326")
    gdf_roads['geom_27700'] = gdf_roads['geometry'].to_crs("EPSG:27700")
    gdf_roads = gdf_roads.rename(columns={'geometry': 'geom_4326'}).set_geometry('geom_4326')
    gdf_roads.to_postgis("uk_roads", con=engine, if_exists="replace", index=False)
    print(f"💾 Saved {len(gdf_roads)} total unique roads across all regions.")
else:
    print("❌ No roads collected.")

if all_buildings:
    df_b = pd.DataFrame(all_buildings).drop_duplicates(subset=['osm_id'])
    gdf_buildings = gpd.GeoDataFrame(df_b, geometry='geometry', crs="EPSG:4326")
    gdf_buildings['geom_27700'] = gdf_buildings['geometry'].to_crs("EPSG:27700")
    gdf_buildings = gdf_buildings.rename(columns={'geometry': 'geom_4326'}).set_geometry('geom_4326')
    gdf_buildings.to_postgis("uk_buildings", con=engine, if_exists="replace", index=False)
    print(f"💾 Saved {len(gdf_buildings)} total unique building footprints across all regions.")
else:
    print("ℹ️ No building footprints collected in these areas.")

print("\n🎉 Infrastructure processing complete!")