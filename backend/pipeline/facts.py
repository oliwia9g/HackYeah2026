"""Model faktow: kazda informacja o dostepnosci ma zrodlo, date i status.

Zasada z briefu: brak danych NIGDY nie oznacza "dostepne".
Statusy: potwierdzone | prawdopodobne | niezweryfikowane | sprzeczne | brak

Skad bierzemy date ("observed_at"):
  1. check_date / survey:date z tagow OSM  -> observed_basis = "check_date" (ktos swiadomie sprawdzil)
  2. data ostatniej edycji obiektu z Overpass (out meta) -> observed_basis = "last_edit"
     UWAGA: ostatnia edycja moze dotyczyc czegos innego (np. nazwy), wiec to SLABSZY dowod:
     pewnosc nizsza, status najwyzej "prawdopodobne".
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

FACT_COLUMNS = [
    "feature_id",     # np. "node/123456"
    "attribute",      # np. "wheelchair"
    "value",          # np. "yes"
    "source",         # "OpenStreetMap" | "GTFS ZTP" | "zgloszenie uzytkownika" ...
    "source_url",
    "license",
    "retrieved_at",   # kiedy pobralismy
    "observed_at",    # kiedy ktos to sprawdzil albo ostatnio edytowal obiekt - moze byc puste
    "confidence",     # 0..1
    "status",
    "observed_basis",  # "check_date" | "last_edit" | None
    "last_edit_at",    # data ostatniej edycji obiektu w OSM (z Overpass), jesli znana
]

# bazowa wiarygodnosc wg typu zrodla
SOURCE_BASE = {
    "owner": 0.95,        # potwierdzenie wlasciciela obiektu
    "osm_dated": 0.8,     # tag OSM z data weryfikacji (check_date)
    "osm_last_edit": 0.6,  # tylko data ostatniej edycji obiektu
    "osm_undated": 0.5,   # tag OSM bez zadnej daty
    "user_report": 0.3,   # zgloszenie uzytkownika (niezweryfikowane)
}


def parse_date(value) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def months_between(d1: date, d2: date) -> float:
    return (d2 - d1).days / 30.44


def score_osm_fact(observed_at: Optional[date], today: date, fresh_months: int, basis: Optional[str] = "check_date"):
    """Zwraca (confidence, status) dla faktu z OSM."""
    if observed_at is None:
        return SOURCE_BASE["osm_undated"], "prawdopodobne"
    age = months_between(observed_at, today)
    conf = SOURCE_BASE["osm_dated"] if basis == "check_date" else SOURCE_BASE["osm_last_edit"]
    if age > fresh_months:
        # starzenie: tracimy do polowy wiarygodnosci po 3x okresie swiezosci
        conf *= max(0.5, 1 - (age - fresh_months) / (3 * fresh_months))
        return round(conf, 2), "prawdopodobne"
    # sama data ostatniej edycji nie jest potwierdzeniem dostepnosci
    return round(conf, 2), ("potwierdzone" if basis == "check_date" else "prawdopodobne")


def load_osm_meta(raw_dir: Path) -> dict:
    """Wczytuje raw/osm_meta.json (tworzy go pipeline.fetch_overpass_meta). Brak pliku = brak dat edycji."""
    p = Path(raw_dir) / "osm_meta.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8")).get("elements", {})


def make_osm_facts(pois, attributes: list[str], fresh_months: int, meta: Optional[dict] = None) -> pd.DataFrame:
    """pois: GeoDataFrame z indeksem (typ, id) z osmnx.features_from_bbox.
    meta: slownik "node/123" -> {"timestamp": "2024-03-01T12:00:00Z", ...} z Overpass (opcjonalny)."""
    meta = meta or {}
    today = date.today()
    rows = []
    for (el_type, osmid), row in pois.iterrows():
        fid = f"{el_type}/{osmid}"
        last_edit = parse_date((meta.get(fid) or {}).get("timestamp"))
        checked = parse_date(row.get("check_date")) or parse_date(row.get("survey:date"))
        if checked:
            observed, basis = checked, "check_date"
        elif last_edit:
            observed, basis = last_edit, "last_edit"
        else:
            observed, basis = None, None
        for attr in attributes:
            if attr not in pois.columns:
                continue
            val = row.get(attr)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            conf, status = score_osm_fact(observed, today, fresh_months, basis)
            rows.append(
                {
                    "feature_id": fid,
                    "attribute": attr,
                    "value": str(val),
                    "source": "OpenStreetMap",
                    "source_url": f"https://www.openstreetmap.org/{el_type}/{osmid}",
                    "license": "ODbL 1.0",
                    "retrieved_at": today.isoformat(),
                    "observed_at": observed.isoformat() if observed else None,
                    "confidence": conf,
                    "status": status,
                    "observed_basis": basis,
                    "last_edit_at": last_edit.isoformat() if last_edit else None,
                }
            )
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


# TODO (dalszy ciag):
#  - merge_conflicts(): ten sam feature_id+attribute z roznymi wartosciami -> status "sprzeczne"
#    (zgloszenia uzytkownikow i sprzecznosci sa na razie obslugiwane w api/main.py)
#  - fakt "brak": dla POI bez tagu wheelchair API zwraca status "brak", nie "yes"


def drop_noise_buildings(pois, cfg: dict):
    """Budynki bez nazwy i bez zadnego tagu dostepnosci niczego nie wnosza (tysiace anonimowych kamienic) - odrzucamy je.
    Zostaja: budynki z nazwa albo z choc jednym tagiem dostepnosci, oraz wszystkie obiekty innych typow (sklepy, windy itd.)."""
    if "building" not in pois.columns:
        return pois
    other = [c for c in ("amenity", "shop", "tourism", "leisure", "public_transport", "railway", "highway", "healthcare") if c in pois.columns]
    has_other = pois[other].notna().any(axis=1) if other else pd.Series(False, index=pois.index)
    acc_cols = [c for c in cfg["osm"]["fact_attributes"] if c in pois.columns]
    has_acc = pois[acc_cols].notna().any(axis=1) if acc_cols else pd.Series(False, index=pois.index)
    named = pois["name"].notna() if "name" in pois.columns else pd.Series(False, index=pois.index)
    is_building_only = pois["building"].notna() & ~has_other
    drop = is_building_only & ~named & ~has_acc
    if drop.any():
        print(f"  pominieto budynkow bez nazwy i bez tagow dostepnosci: {int(drop.sum())}")
    return pois[~drop]


BUILDING_TAGS = ["name", "building", "addr:street", "addr:housenumber", "addr:city", "addr:postcode", "addr:place"]


def building_footprints(buildings, cfg: dict, exclude_ids: set | None = None) -> dict:
    """Obrysy budynkow (wielokaty) jako GeoJSON: do klikania w mape (wspolrzedne -> budynek -> adres i cechy).
    buildings: GeoDataFrame z indeksem (typ, id). Zostaja tylko Polygon/MultiPolygon. Wlasciwosci: feature_id, nazwa, rodzaj, adres
    oraz tagi dostepnosci z config.yaml (fact_attributes), zeby klik mogl pokazac udogodnienia nawet dla budynku, ktorego nie ma wsrod POI."""
    import shapely
    from shapely.geometry import mapping

    acc = [c for c in cfg["osm"]["fact_attributes"] if c in buildings.columns]
    keep = [c for c in BUILDING_TAGS if c in buildings.columns] + acc
    feats = []
    for (el_type, osmid), row in buildings.iterrows():
        g = row.geometry
        if g is None or g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        fid = f"{el_type}/{osmid}"
        props = {"feature_id": fid}
        for c in keep:
            v = row.get(c)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                props[c] = str(v)
        g = shapely.set_precision(g, 1e-6)
        feats.append({"type": "Feature", "geometry": mapping(g), "properties": props})
    return {"type": "FeatureCollection", "features": feats}
