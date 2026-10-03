"""NMT z Geoportalu (GUGiK) -> nachylenie krawedzi sieci pieszej.

Uruchomienie (z katalogu backend/), PO pipeline.fetch_osm:
    python -m pipeline.fetch_dem                 # pobiera NMT przez WCS i liczy nachylenie
    python -m pipeline.fetch_dem --res 1         # gestsza siatka (1 m), wiekszy plik
    python -m pipeline.fetch_dem --file sciezka/do/nmt.tif   # NMT pobrany recznie z Geoportalu

Dodaje do edges.geojson kolumny:
    incline_signed_pct  - nachylenie ze znakiem wzdluz kierunku krawedzi (+ pod gore)
    incline_pct         - nachylenie bezwzgledne uzywane przez routing
    incline_src         - skad: "OSM" | "NMT" | "NMT_krotka_krawedz" | "most_tunel_zalozono_plasko"

UWAGA: skrypt nie byl testowany na zywym serwisie GUGiK (z mojego srodowiska nie ma dostepu).
Jesli WCS zwroci blad, skrypt wypisze odpowiedz serwera. Plan B: pobierz NMT recznie
z geoportal.gov.pl (Pobieranie danych -> NMT) i uzyj --file.
"""
from __future__ import annotations

import argparse
import math
import sys

import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer

from pipeline.common import bbox_tuple, load_config, out_dir, raw_dir, write_geojson

WCS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF"
COVERAGE = "DTM_PL-KRON86-NH_TIFF"   # z GetCapabilities
CRS_M = "EPSG:2180"
MIN_RELIABLE_LEN_M = 10.0            # krotsze krawedzie: nachylenie z NMT jest zaszumione


def fetch_wcs(cfg: dict, res_m: float):
    t = Transformer.from_crs("EPSG:4326", CRS_M, always_xy=True)
    w, s, e, n = bbox_tuple(cfg)
    pts = [t.transform(x, y) for x, y in [(w, s), (w, n), (e, s), (e, n)]]
    xs, ys = zip(*pts)
    pad = 50  # zapas, zeby krawedzie na brzegu mialy wysokosc
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    width = int(math.ceil((maxx - minx) / res_m))
    height = int(math.ceil((maxy - miny) / res_m))
    params = {
        "SERVICE": "WCS", "VERSION": "1.0.0", "REQUEST": "GetCoverage",
        "COVERAGE": COVERAGE, "CRS": CRS_M,
        "BBOX": f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f}",   # WCS 1.0.0: x,y (E,N)
        "WIDTH": width, "HEIGHT": height, "FORMAT": "image/tiff",
    }
    print(f"pobieram NMT przez WCS ({width}x{height} px, {res_m} m)...")
    r = requests.get(WCS_URL, params=params, timeout=180)
    ctype = r.headers.get("content-type", "").lower()
    if r.status_code != 200 or "tif" not in ctype:
        print("WCS nie zwrocil GeoTIFF-a.")
        print("status:", r.status_code, "content-type:", ctype)
        print(r.text[:1000])
        print("\nPlan B: pobierz NMT recznie z geoportal.gov.pl i uruchom z --file")
        sys.exit(1)
    path = raw_dir(cfg) / "nmt.tif"
    path.write_bytes(r.content)
    print(f"zapisano {path} ({len(r.content) / 1e6:.1f} MB)")
    return path


def sample_dem(ds, xy: list[tuple[float, float]]) -> np.ndarray:
    vals = np.array([v[0] for v in ds.sample(xy)], dtype=float)
    if ds.nodata is not None:
        vals[vals == ds.nodata] = np.nan
    vals[np.abs(vals) > 5000] = np.nan   # sanity check: smieci/NoData
    return vals


def parse_osm_incline(v):
    """OSM: '5%', '5', '-3%' -> liczba; 'up'/'down' -> None."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).strip().replace(",", ".").replace("%", "")
    try:
        return abs(float(s))
    except ValueError:
        return None


def is_flat_structure(row) -> bool:
    """Mosty i tunele: NMT opisuje teren pod spodem, wiec nachylenie bylo by bledne."""
    for col in ("bridge", "tunnel"):
        v = row.get(col)
        if v is not None and not (isinstance(v, float) and np.isnan(v)) and str(v).lower() not in ("no", "none", ""):
            return True
    return False


def compute_incline(edges, dem_path) -> pd.DataFrame:
    edges_m = edges.to_crs(CRS_M)
    starts = [g.coords[0][:2] for g in edges_m.geometry]
    ends = [g.coords[-1][:2] for g in edges_m.geometry]
    lengths = edges_m.geometry.length.to_numpy()

    with rasterio.open(dem_path) as ds:
        if ds.crs is not None and ds.crs.to_string() != CRS_M:
            print(f"UWAGA: NMT ma CRS {ds.crs}, a oczekiwano {CRS_M} - sprawdz przed uzyciem")
        z0 = sample_dem(ds, starts)
        z1 = sample_dem(ds, ends)

    with np.errstate(divide="ignore", invalid="ignore"):
        signed = np.where(lengths > 0, (z1 - z0) / lengths * 100.0, np.nan)

    res = edges.copy()
    res["incline_signed_pct"] = np.round(signed, 1)
    nmt_abs = np.abs(signed)

    inc, src = [], []
    for i, (_, row) in enumerate(edges.iterrows()):
        osm = parse_osm_incline(row.get("incline"))
        if is_flat_structure(row):
            inc.append(0.0); src.append("most_tunel_zalozono_plasko")
        elif osm is not None:
            inc.append(osm); src.append("OSM")
        elif np.isnan(nmt_abs[i]):
            inc.append(np.nan); src.append("brak")
        elif lengths[i] < MIN_RELIABLE_LEN_M:
            inc.append(round(float(nmt_abs[i]), 1)); src.append("NMT_krotka_krawedz")
        else:
            inc.append(round(float(nmt_abs[i]), 1)); src.append("NMT")
    res["incline_pct"] = inc
    res["incline_src"] = src
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="lokalny GeoTIFF/ASC z NMT (EPSG:2180) zamiast WCS")
    ap.add_argument("--res", type=float, default=2.0, help="rozdzielczosc siatki w metrach (WCS)")
    args = ap.parse_args()

    cfg = load_config()
    edges_pkl = raw_dir(cfg) / "edges.pkl"
    if not edges_pkl.exists():
        print("Brak edges.pkl - najpierw uruchom: python -m pipeline.fetch_osm")
        sys.exit(1)
    edges = pd.read_pickle(edges_pkl)

    dem_path = args.file or fetch_wcs(cfg, args.res)
    result = compute_incline(edges, dem_path)

    print("\n=== NACHYLENIE (obszar demo) ===")
    print(result["incline_src"].value_counts().to_string())
    valid = result["incline_pct"].dropna()
    for thr in (3, 6, 8, 12):
        print(f"  krawedzie > {thr:2d}% : {(valid > thr).sum():5d} ({100 * (valid > thr).mean():.1f}%)")

    result.to_pickle(raw_dir(cfg) / "edges_incline.pkl")
    write_geojson(result, out_dir(cfg) / "edges.geojson")


if __name__ == "__main__":
    main()
