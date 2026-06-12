import io
import urllib.parse  # <-- Add this import at the top
import pandas as pd
import requests
from sqlalchemy import create_engine, text

# 1. Configuration Settings
MAP_KEY = "db9b0ba991150c2b2b68ebdebd3e9843"
RAW_PASSWORD = "anita-geoai"  # <-- Put your raw password here

# This safely translates symbols like @ to %40 so the database engine can read it
encoded_password = urllib.parse.quote_plus(RAW_PASSWORD)

# Database Connection Details
USERNAME = "postgres"
HOST = "127.0.0.1"
PORT = "5433"
DATABASE = "uk_cat_model"

# Use the encoded_password variable here
connection_string = (
    f"postgresql://{USERNAME}:{encoded_password}@{HOST}:{PORT}/{DATABASE}"
)
engine = create_engine(connection_string)


# 2. Define the NASA Area API parameters
# Approximate bounding box for the UK: [West, South, East, North]
uk_bbox = "-11,49,2,62"
satellite_source = "VIIRS_SNPP_NRT"
range_days = "5"  # The Area API allows up to 5 days of data per request

# Updated URL structure targeting the active 'area' endpoint
nasa_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{satellite_source}/{uk_bbox}/{range_days}"

print("📡 Requesting live data from NASA FIRMS Area API for the UK region...")

# 3. Fetch data directly from NASA
response = requests.get(nasa_url)

if response.status_code == 200:
    # Check if the server returned the error string instead of data
    if "invalid api calls" in response.text.lower():
        print("❌ NASA rejected the call. Please verify your MAP_KEY is correct.")
    else:
        print("✅ Data successfully retrieved from NASA!")
        csv_data = io.StringIO(response.text)
        df = pd.read_csv(csv_data)

        if df.empty:
            print("ℹ️ No active fires detected in the UK bounding box over the last 5 days.")
        else:
            print(f"🔥 Found {len(df)} fire points in the region. Filtering and processing...")

            # Ensure we only keep columns that match our PostGIS database schema
            df = df[["latitude", "longitude", "acq_date", "frp"]]
            df["acq_date"] = pd.to_datetime(df["acq_date"])

            # 4. Insert directly into PostGIS
            print("📥 Streaming data directly into PostGIS...")
            df.to_sql("uk_wildfires", con=engine, if_exists="append", index=False)

            # 5. Run PostGIS spatial calculations
            spatial_query = """
                UPDATE uk_wildfires 
                SET geom_4326 = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                WHERE geom_4326 IS NULL;

                UPDATE uk_wildfires 
                SET geom_27700 = ST_Transform(geom_4326, 27700)
                WHERE geom_27700 IS NULL;
            """
            print("🗺️ Transforming coordinates to British National Grid (meters)...")
            with engine.begin() as connection:
                connection.execute(text(spatial_query))

            print("🎉 Ingestion complete! Geometries created and spatially indexed.")
else:
    print(f"❌ Failed to fetch data from NASA. HTTP Error Code: {response.status_code}")