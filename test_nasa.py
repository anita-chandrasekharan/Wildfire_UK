import requests

MAP_KEY = "db9b0ba991150c2b2b68ebdebd3e9843"  # <-- Put your key here
test_url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{MAP_KEY}/VIIRS_SNPP_NRT/GBR/1"

print("Testing connection to NASA FIRMS...")
response = requests.get(test_url)

print(f"Status Code: {response.status_code}")
print("Response Text from NASA:")
print(response.text)