# NOTES.md — Surprises, Bug Fixes, and Learnings

This file tracks unexpected findings and fixes during development. It feeds the README "Learnings" section.

## Phase 0 — Bootstrap & Spike

- **uv install:** `pip install uv` worked cleanly. uv 0.12.23 installed.
- **Package install:** 44 packages resolved and installed in ~3.5 min. Key versions: geopandas 1.2.0, pyogrio 0.13.0, shapely 2.1.2, pyproj 3.8.0, fastapi 0.142.2, sqlalchemy 2.1.3.
- **GDAL drivers:** 64 drivers available. KML and ESRI Shapefile both readable. No manual driver enabling needed.
- **KML read:** pyogrio reads KML with CRS EPSG:4326 automatically. Columns include GDAL-specific fields (id, Name, description, timestamp, begin, end, altitudeMode, tessellate, extrude, visibility, drawOrder, icon, geometry).
- **pyproj:** EPSG:32643 resolves to "WGS 84 / UTM zone 43N". `is_projected` and `is_geographic` work as expected.
- **UTM logic:** Mumbai→32643, London→32630, Sydney→32756 all correct.
- **Shapefile zip:** Deferred to Phase 2 — need proper fixtures with .shp/.shx/.dbf/.prj files.

## Phase 1 — Geo Domain

- **utm_epsg_for lon normalization:** The naive `((lon + 180) % 360) - 180` maps both -180 and +180 to -180, which collapses zone 60's east edge into zone 1. Fix: only normalize out-of-range values, keep exact +/-180 as-is. -180 is the west edge of zone 1, +180 is the east edge of zone 60.
- **pd.NaT is a datetime subclass:** `isinstance(pd.NaT, datetime.datetime)` is True, so the datetime branch in `json_safe` caught NaT first and returned the string "NaT". Fix: explicit `value is pd.NaT` check BEFORE the datetime branch.
- **shapely.ops.transform vs pyproj:** `shapely.ops.transform(transformer.transform, geom)` silently failed with pyproj transformers in Shapely 2. Fix: walk the GeoJSON coordinates manually and call `transformer.transform(x, y)` on each pair.
- **shapely.get_coordinates returns 2D array:** `math.isfinite(c) for c in coords` fails — need `np.all(np.isfinite(coords))`.
- **shapely mapping returns tuples:** `mapping(geom)` returns nested tuples, not lists. Fix: recursive `_convert_coords` that converts tuples to lists.
- **UTM accuracy:** Mumbai test polygon in EPSG:3857 measures ~889k m² vs ~1M m² expected — Web Mercator inflates by 1/cos²(lat). This confirms why we always reproject to local UTM.
- **Lat boundary tests fixed:** 83.9°N is zone 31 (EPSG:32631), not 32660. -80° is zone 31 south (32731), UPS South starts below -80.
- **Build backend:** uv_build expected `src/` layout. Switched to hatchling with `packages = ["app"]`.
- **Ruff BLE001:** Narrowed `except Exception` to `pyproj.exceptions.ProjError` and `(ProjError, ValueError)` in measure.py.

## Phase 2 — Readers & Archive

- **GDAL keeps geometry-less Placemarks:** `pyogrio.read_dataframe` returns the row with `geometry=None` instead of skipping it. Good — feature count matches the Placemark count, and `measure_geometry(None)` already returns UNSUPPORTED.
- **KML CRS is always EPSG:4326:** Driver reports it automatically; set explicitly per the KML spec. Altitude preserved on read (has_z=True), measurement forces 2D.
- **MultiGeometry → GeometryCollection:** GDAL maps KML `<MultiGeometry>` to a GeometryCollection with named parts — our UNSUPPORTED-with-reason path handles it.
- **Zip Slip on Windows:** `Path("../../evil.sh").parts` works on Windows but `Path("/tmp/evil.shp").is_absolute()` misses POSIX paths when running on Windows. Fix: check both PurePosixPath and PureWindowsPath, plus leading `/` or `\`.
- **Skip-vs-unsafe ordering matters:** `..` in `_is_skipped` dotfile check swallowed `../../evil.sh` before the unsafe check saw it. Fix: run `_is_unsafe` FIRST, then skip dotfiles (excluding `.` and `..` from the dotfile rule).
- **pyogrio CRS is None (not an exception):** Missing or garbage `.prj` reads fine with `crs=None`. The assume-4326 policy checks every coordinate is valid lon/lat via `shapely.get_coordinates`.
- **pyogrio error types:** Malformed KML raises `pyogrio.errors.DataSourceError`; catch `DataSourceError` + `DataLayerError` and wrap in our `InvalidGeoDataError`.
- **ArchiveError now subclasses InvalidArchiveError:** Readers raise `InvalidArchiveError` directly for missing parts, so archive safety errors flow through the same 422 envelope.

## Phase 3 — Persistence & Ingestion

- **Routes are plain `def`, so storage stays sync:** The plan says endpoints are plain def so GDAL work runs in the threadpool. That means `storage.save_upload` takes a binary file-like (`UploadFile.file`, `BytesIO` in tests) — no async iterator plumbing needed.
- **Magic-byte sniffing, not Content-Type:** Zip magic (`PK\x03\x04` etc.) and `<` after BOM/whitespace strip for KML. A `.zip` with text content hits 422 with a FAILED record, not 415.
- **Validation errors before any record:** 415/400/413 raise before the PROCESSING insert, so "nothing persisted" tests assert zero FileRecords.
- **`_mark_failed` re-fetches the record:** After `rollback()`, the in-memory object is detached — `db.get(FileRecord, id)` before setting FAILED status.
- **`bulk_insert_mappings` in batches of 1000:** Per the plan; mappings built from measured features with file-wide 0-based index.
- **Per-feature exceptions become ERROR:** `_safe_measure` catches everything (noqa BLE001, intentional by design) so one bad geometry never fails the file.
- **Temp dirs always cleaned:** `TemporaryDirectory` context manager wraps `safe_extract`+read, so hostile zips leave no leaked dirs.
- **Error messages carry no paths:** Tests assert "tmp"/"uploads" absent from `error_message`; `file_id` travels in `error.details` instead.
