import os
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
from shapely.wkt import loads as load_wkt

# 1. Target Directory Configuration
TARGET_DIR = r"E:\GeoAI\Wildfire_UK\data"
os.makedirs(TARGET_DIR, exist_ok=True)

# 2. Database Connection (Update with your real password and database name!)
DATABASE_URL = "postgresql://postgres:anita-geoai@localhost:5433/uk_cat_model"
engine = create_engine(DATABASE_URL)

print("🔗 Connected to PostGIS database successfully.")

csv_path = os.path.join(TARGET_DIR, "wildfire_data.csv")
infra_path = os.path.join(TARGET_DIR, "infrastructure_assets.geojson")
roads_path = os.path.join(TARGET_DIR, "uk_roads.geojson")

# =====================================================================
# 3. Export Wildfires (CSV)
# =====================================================================
try:
    print("\n⏳ 1/3: Exporting wildfire data to CSV...")
    df = pd.read_sql("SELECT * FROM uk_wildfires", engine)
    df.to_csv(csv_path, index=False)
    print(f"✅ Saved: {csv_path}")
except Exception as e:
    print(f"❌ Error exporting CSV: {e}")

# =====================================================================
# 4. Export Infrastructure (GeoJSON via WKT Bypass)
# =====================================================================
try:
    print("\n⏳ 2/3: Exporting infrastructure assets...")
    query_infra = "SELECT *, ST_AsText(geom_4326) as wkt_geom FROM uk_buildings"
    df_infra = pd.read_sql(query_infra, engine)
    
    if 'geom_4326' in df_infra.columns:
        df_infra = df_infra.drop(columns=['geom_4326'])
        
    df_infra['geometry'] = df_infra['wkt_geom'].apply(load_wkt)
    gdf_infra = gpd.GeoDataFrame(df_infra, geometry='geometry')
    gdf_infra = gdf_infra.drop(columns=['wkt_geom'])
    
    gdf_infra.to_file(infra_path, driver="GeoJSON")
    print(f"✅ Saved: {infra_path}")
except Exception as e:
    print(f"❌ Error exporting Infrastructure: {e}")

# =====================================================================
# 5. Export UK Roads (GeoJSON via WKT Bypass)
# =====================================================================
try:
    print("\n⏳ 3/3: Exporting UK road networks...")
    # Assuming your roads table uses the same 'geom_4326' column name layout
    query_roads = "SELECT *, ST_AsText(geom_4326) as wkt_geom FROM uk_roads"
    df_roads = pd.read_sql(query_roads, engine)
    
    if 'geom_4326' in df_roads.columns:
        df_roads = df_roads.drop(columns=['geom_4326'])
        
    print("🔄 Processing linear road segments (this may take a moment)...")
    df_roads['geometry'] = df_roads['wkt_geom'].apply(load_wkt)
    gdf_roads = gpd.GeoDataFrame(df_roads, geometry='geometry')
    gdf_roads = gdf_roads.drop(columns=['wkt_geom'])
    
    gdf_roads.to_file(roads_path, driver="GeoJSON")
    print(f"✅ Saved: {roads_path}")
except Exception as e:
    print(f"❌ Error exporting Roads: {e}")

# =====================================================================
# 6. Final Status Check
# =====================================================================
print("\n🔍 Final check of data folder contents:")
print(os.listdir(TARGET_DIR))

print("\n🚀 Opening data folder...")
os.startfile(TARGET_DIR)