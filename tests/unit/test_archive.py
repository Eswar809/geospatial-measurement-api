"""Unit tests for safe zip extraction."""

import zipfile

import pytest

from app.services.archive import ArchiveError, safe_extract


def _make_zip(path, members):
    """Create a zip from a {name: bytes} mapping."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _shapefile_parts(body=b"fake"):
    return {
        "parcels.shp": body,
        "parcels.shx": body,
        "parcels.dbf": body,
    }


class TestSafeExtract:
    def test_happy_path(self, tmp_path):
        zip_path = _make_zip(tmp_path / "ok.zip", _shapefile_parts())
        dest = safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)
        assert (dest / "data.shp").exists()
        assert (dest / "data.shx").exists()
        assert (dest / "data.dbf").exists()

    def test_uppercase_extensions(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "upper.zip",
            {"P.SHP": b"x", "P.SHX": b"x", "P.DBF": b"x"},
        )
        dest = safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)
        assert (dest / "data.shp").exists()

    def test_nested_paths_flattened(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "nested.zip",
            {"a/b/parcels.shp": b"x", "parcels.shx": b"x", "parcels.dbf": b"x"},
        )
        dest = safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)
        assert (dest / "data.shp").exists()

    def test_skips_macosx_and_dotfiles(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "mac.zip",
            {
                **_shapefile_parts(),
                "__MACOSX/._parcels.shp": b"junk",
                ".DS_Store": b"junk",
            },
        )
        dest = safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)
        assert (dest / "data.shp").read_bytes() == b"fake"

    def test_zip_slip_rejected(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "evil.zip",
            {**_shapefile_parts(), "../../evil.sh": b"pwn"},
        )
        with pytest.raises(ArchiveError, match="unsafe"):
            safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)

    def test_absolute_path_rejected(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "abs.zip",
            {**_shapefile_parts(), "/tmp/evil.shp": b"pwn"},
        )
        with pytest.raises(ArchiveError, match="unsafe"):
            safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)

    def test_too_many_members(self, tmp_path):
        members = {f"f{i}.txt": b"x" for i in range(5)}
        members.update(_shapefile_parts())
        zip_path = _make_zip(tmp_path / "many.zip", members)
        with pytest.raises(ArchiveError, match="too many"):
            safe_extract(zip_path, tmp_path / "out", max_entries=3, max_bytes=10**6)

    def test_uncompressed_cap_counts_bytes_written(self, tmp_path):
        zip_path = _make_zip(tmp_path / "big.zip", _shapefile_parts(body=b"x" * 5000))
        with pytest.raises(ArchiveError, match="exceeds"):
            safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=100)

    def test_no_shp_rejected(self, tmp_path):
        zip_path = _make_zip(tmp_path / "noshp.zip", {"a.dbf": b"x", "a.shx": b"x"})
        with pytest.raises(ArchiveError, match="no .shp"):
            safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)

    def test_missing_companion_rejected_later(self, tmp_path):
        # Extraction keeps what exists; the reader enforces .shx/.dbf presence.
        zip_path = _make_zip(tmp_path / "noshx.zip", {"a.shp": b"x", "a.dbf": b"x"})
        dest = safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)
        assert (dest / "data.shp").exists()
        assert not (dest / "data.shx").exists()

    def test_two_shp_rejected(self, tmp_path):
        zip_path = _make_zip(
            tmp_path / "two.zip",
            {"a.shp": b"x", "b.shp": b"y", "a.shx": b"x", "a.dbf": b"x"},
        )
        with pytest.raises(ArchiveError, match="more than one"):
            safe_extract(zip_path, tmp_path / "out", max_entries=50, max_bytes=10**6)

    def test_corrupt_zip_rejected(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip at all")
        with pytest.raises(ArchiveError, match="corrupt"):
            safe_extract(bad, tmp_path / "out", max_entries=50, max_bytes=10**6)
