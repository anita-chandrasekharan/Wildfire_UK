# 🇬🇧 UK Wildfire Predictive GeoAI Catastrophe Dashboard

An advanced, real-time spatial predictive application designed to evaluate critical industrial infrastructure vulnerability against satellite-derived wildfire thermal anomalies across the United Kingdom.

## 🚀 Architectural Overview
This system couples a high-performance **PostGIS** spatial backend with an interactive Python **Streamlit** dashboard. Instead of relying on static isotropic (circular) risk buffers, the model uses an **anisotropic plume simulation engine** powered by meteorological vectors (wind velocity and bearing angle) to forecast directional fire spread boundaries on the fly. 

Using an automated spatial routing mechanics pipeline, any infrastructure assets (OpenStreetMap structural footprints) intersecting the predicted danger vector are instantly evaluated using a weighted multi-criteria **Asset Vulnerability Index ($V_i$)**.

## 🛠️ Tech Stack
* **Spatial Database:** PostgreSQL 16 + PostGIS 3.4
* **Dashboard Interface:** Streamlit (Python Web Framework)
* **Geospatial Processing Engine:** GeoPandas, Shapely (Affinity Transformations), PyProj
* **Interactive Map Visualization:** Folium (LeafletJS wrapper)

## ⚡ Core Features
1. **Dynamic Metric Buffering:** Performs projection transformations from geographic `EPSG:4326` to British National Grid `EPSG:27700` in real-time to guarantee mathematically precise metric spacing operations.
2. **Anisotropic Plume Modeling:** Uses wind vector arrays to translate, scale, and rotate fire spread perimeters downwind.
3. **Optimized Spatial Architecture:** Implemented PostGIS GiST indexing and runtime checkboxes to prevent client-side browser performance degradation (vector bloat).

## 🔨 Setup & Installation

1. **Clone the Repository:**
   ```bash
   git clone [https://github.com/dspawar/wildfire-geoai-catastrophe-dashboard.git](https://github.com/dspawar/wildfire-geoai-catastrophe-dashboard.git)
   cd wildfire-geoai-catastrophe-dashboard

 1.  Configure Environment & Dependencies:
  ```bash
   conda create -n geoai_bigdata_env python=3.10
    conda activate geoai_bigdata_env
    pip install -r requirements.txt

 2.   Run the Application:
    ```bash
    streamlit run src/app.py