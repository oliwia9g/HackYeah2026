"""Model faktów: każda informacja o dostępności ma źródło, datę i status.

Zasada z briefu: brak danych NIGDY nie oznacza "dostępne".
Statusy: potwierdzone | prawdopodobne | niezweryfikowane | sprzeczne | brak
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd

FACT_COLUMNS = [
    "feature_id",     # np. "node/123456"
    "attribute",      # np. "wheelchair"
    "value",          # np. "yes"
    "source",         # "OpenStreetMap" | "GTFS ZTP" | "zgłoszenie użytkownika" ...
    "source_url",
    "license",
    "retrieved_at",   # kiedy pobraliśmy
    "observed_at",    # kiedy ktoś to sprawdził (check_date/survey:date) - może być puste
    "confidence",     # 0..1
    "status",
]

# bazowa wiarygodność wg typu źródła
SOURCE_BASE = {
    "owner": 0.95,        # potwierdzenie właściciela obiektu
    "osm_dated": 0.8,     # tag OSM z datą weryfikacji
    "osm_undated": 0.5,   # tag OSM bez daty
    "user_report": 0.3,   # zgłoszenie użytkownika (niezweryfikowane)
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


def score_osm_fact(observed_at: Optional[date], today: date, fresh_months: int):
    """Zwraca (confidence, status) dla faktu z OSM."""
    if observed_at is None:
        return SOURCE_BASE["osm_undated"], "prawdopodobne"
    age = months_between(observed_at, today)
    conf = SOURCE_BASE["osm_dated"]
    if age > fresh_months:
        # starzenie: tracimy do połowy wiarygodności po 3x okresie świeżości
        conf *= max(0.5, 1 - (age - fresh_months) / (3 * fresh_months))
        return round(conf, 2), "prawdopodobne"
    return round(conf, 2), "potwierdzone"


def make_osm_facts(pois, attributes: list[str], fresh_months: int) -> pd.DataFrame:
    """pois: GeoDataFrame z indeksem (element_type, osmid) z osmnx.features_from_bbox."""
    today = date.today()
    rows = []
    for (el_type, osmid), row in pois.iterrows():
        observed = parse_date(row.get("check_date")) or parse_date(row.get("survey:date"))
        for attr in attributes:
            if attr not in pois.columns:
                continue
            val = row.get(attr)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            conf, status = score_osm_fact(observed, today, fresh_months)
            rows.append(
                {
                    "feature_id": f"{el_type}/{osmid}",
                    "attribute": attr,
                    "value": str(val),
                    "source": "OpenStreetMap",
                    "source_url": f"https://www.openstreetmap.org/{el_type}/{osmid}",
                    "license": "ODbL 1.0",
                    "retrieved_at": today.isoformat(),
                    "observed_at": observed.isoformat() if observed else None,
                    "confidence": conf,
                    "status": status,
                }
            )
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


# TODO (dalszy ciąg):
#  - merge_conflicts(): ten sam feature_id+attribute z różnymi wartościami -> status "sprzeczne"
#  - add_user_reports(): zgłoszenia użytkowników (status "niezweryfikowane")
#  - fakt "brak": dla POI bez tagu wheelchair wystawiamy status "brak", nie "yes"
