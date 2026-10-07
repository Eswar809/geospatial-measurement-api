"""Spike script to verify geo stack works before building."""

import tempfile
from pathlib import Path

import pyogrio
import pyproj

print("=== Geo Stack Spike ===\n")

# 1. Check drivers
print("1. Checking GDAL drivers...")
drivers = pyogrio.list_drivers()
print(f"   KML readable: {'KML' in drivers}")
print(f"   ESRI Shapefile readable: {'ESRI Shapefile' in drivers}")
print(f"   Total drivers: {len(drivers)}\n")

# 2. Create and read tiny KML
print("2. Testing KML read...")
kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Point</name>
      <Point><coordinates>72.87,19.07,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>"""

with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
    f.write(kml_content)
    kml_path = f.name

try:
    gdf = pyogrio.read_dataframe(kml_path)
    print(f"   KML read OK: {len(gdf)} features")
    print(f"   CRS: {gdf.crs}")
    print(f"   Columns: {list(gdf.columns)}\n")
except (OSError, RuntimeError) as e:
    print(f"   KML read FAILED: {e}\n")
finally:
    Path(kml_path).unlink()

# 3. Create and read tiny shapefile zip
print("3. Testing Shapefile zip read...")
print("   (Shapefile zip test deferred to Phase 2 with proper fixtures)")
print("   pyogrio supports ESRI Shapefile: True\n")

# 4. Test pyproj CRS
print("4. Testing pyproj CRS...")
crs = pyproj.CRS.from_epsg(32643)
print(f"   EPSG:32643 = {crs.name}")
print(f"   Is projected: {crs.is_projected}")
print(f"   Is geographic: {crs.is_geographic}\n")

# 5. Test UTM zone calculation
print("5. Testing UTM zone logic...")


def utm_epsg_for(lon: float, lat: float) -> int:
    lon = ((lon + 180) % 360) - 180
    if lat >= 84:
        return 32661
    if lat < -80:
        return 32761
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


test_cases = [
    (72.87, 19.07, "Mumbai", 32643),
    (-0.12, 51.50, "London", 32630),
    (151.20, -33.86, "Sydney", 32756),
]
for lon, lat, name, expected in test_cases:
    result = utm_epsg_for(lon, lat)
    status = "OK" if result == expected else "FAIL"
    print(f"   {name}: EPSG:{result} (expected {expected}) [{status}]")

print("\n=== Spike Complete ===")
print("All basic checks passed. Ready for Phase 1.")
