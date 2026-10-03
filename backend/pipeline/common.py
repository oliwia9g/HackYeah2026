"""Wspólne helpery: konfiguracja, ścieżki, zapis GeoJSON."""
from pathlib import Path
import json

import yaml

ROOT = Path(__file__).resolve().parents[1]  # backend/


def _read_aoi(path: Path):
    """Wielokat AOI z GeoJSON-a -> WGS84. Czyta CRS zapisany w pliku (np. urn:...EPSG::2180)."""
    from pyproj import CRS, Transformer
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    gj = json.loads(path.read_text("utf-8"))
    if gj.get("type") == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in gj["features"]]
    elif gj.get("type") == "Feature":
        geoms = [shape(gj["geometry"])]
    else:
        geoms = [shape(gj)]
    g = unary_union(geoms)
    crs_name = ((gj.get("crs") or {}).get("properties") or {}).get("name") or "EPSG:4326"
    src = CRS.from_user_input(crs_name)
    if src.to_epsg() != 4326:
        g = transform(Transformer.from_crs(src, 4326, always_xy=True).transform, g)
    return g.buffer(0)   # naprawia drobne bledy topologii


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("aoi"):
        poly = _read_aoi(ROOT / cfg["aoi"])
        w, s, e, n = poly.bounds
        cfg["bbox"] = {"west": w, "south": s, "east": e, "north": n}   # prostokat otaczajacy AOI
        cfg["_aoi_geom"] = poly
    return cfg


def load_aoi(cfg: dict):
    """Wielokat obszaru demo w WGS84 (shapely). Bez klucza aoi w konfiguracji: prostokat z bbox."""
    if cfg.get("_aoi_geom") is not None:
        return cfg["_aoi_geom"]
    from shapely.geometry import box
    return box(*bbox_tuple(cfg))


def query_aoi(cfg: dict, margin_deg: float = 8e-5):
    """Prosty wielokat (kilkadziesiat wierzcholkow) do ZAPYTAN sieciowych: AOI powiekszone o ok. 9 m i uproszczone.
    Zawsze w calosci przykrywa AOI; dokladne przyciecie do AOI robimy potem lokalnie, wiec nic nie tracimy."""
    aoi = load_aoi(cfg)
    q = aoi.buffer(margin_deg, join_style="mitre", mitre_limit=2).simplify(margin_deg, preserve_topology=True)
    if not q.contains(aoi):                      # zabezpieczenie: gdyby uproszczenie cos uciely, uzyj wypuklej otoczki
        q = aoi.convex_hull.buffer(margin_deg)
    return q


def inside_aoi(cfg: dict, lon: float, lat: float) -> bool:
    import shapely
    return bool(shapely.contains_xy(load_aoi(cfg), lon, lat))


def bbox_tuple(cfg: dict) -> tuple:
    """(left, bottom, right, top) - kolejność wymagana przez osmnx 2.x."""
    b = cfg["bbox"]
    return (b["west"], b["south"], b["east"], b["north"])


def raw_dir(cfg: dict) -> Path:
    p = ROOT / cfg["paths"]["raw"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def out_dir(cfg: dict) -> Path:
    p = (ROOT / cfg["paths"]["out"]).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def clean_for_geojson(gdf):
    """GeoJSON nie lubi list/słowników/dat w kolumnach - zamieniamy na tekst."""
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        if gdf[col].dtype == "object":
            gdf[col] = gdf[col].apply(
                lambda v: json.dumps(v, ensure_ascii=False)
                if isinstance(v, (list, dict, set, tuple))
                else v
            )
        elif "datetime" in str(gdf[col].dtype):
            gdf[col] = gdf[col].astype(str)
    return gdf


def write_geojson(gdf, path: Path) -> None:
    gdf = clean_for_geojson(gdf)
    gdf.to_file(path, driver="GeoJSON")
    print(f"zapisano {path} ({len(gdf)} obiektów)")
