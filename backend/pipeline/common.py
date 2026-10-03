"""Wspólne helpery: konfiguracja, ścieżki, zapis GeoJSON."""
from pathlib import Path
import json

import yaml

ROOT = Path(__file__).resolve().parents[1]  # backend/


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
