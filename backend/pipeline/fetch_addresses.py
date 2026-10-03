"""Buduje lokalny indeks adresow i ulic dla geokodowania (wyszukiwanie po adresie zamiast klikania w mape).

Zrodlo: OpenStreetMap (addr:street + addr:housenumber oraz nazwy ulic z grafu pieszego).
Wynik: raw/addresses.json (nie idzie do gita). Uruchom PO pipeline.fetch_osm (potrzebuje raw/edges.pkl):
    python -m pipeline.fetch_addresses
"""
from __future__ import annotations

import json
from datetime import date

import osmnx as ox
import pandas as pd

from pipeline.common import load_aoi, load_config, query_aoi, raw_dir, with_overpass_fallback


def _s(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    v = str(v).strip()
    return v or None


def fetch_addresses(cfg: dict) -> list[dict]:
    print("pobieram punkty adresowe z OSM...")
    g = with_overpass_fallback(ox.features_from_polygon, query_aoi(cfg), {"addr:housenumber": True})
    g = g[g.geometry.representative_point().within(load_aoi(cfg))]
    print(f"  obiektow z numerem: {len(g)}")
    pts = g.geometry.representative_point()
    out = []
    for (el_type, osmid), row in g.iterrows():
        street = _s(row.get("addr:street")) or _s(row.get("addr:place"))
        number = _s(row.get("addr:housenumber"))
        if not street or not number:
            continue
        p = pts.loc[(el_type, osmid)]
        out.append({"id": f"{el_type}/{osmid}", "type": "adres", "street": street, "number": number,
                    "city": _s(row.get("addr:city")), "postcode": _s(row.get("addr:postcode")),
                    "lon": round(p.x, 6), "lat": round(p.y, 6)})
    return out


def streets_from_graph(raw) -> list[dict]:
    """Jedna pozycja na nazwe ulicy: punkt w polowie najdluzszego odcinka."""
    edges = pd.read_pickle(raw / "edges.pkl")
    best: dict = {}
    for name, geom, length in zip(edges["name"], edges.geometry, edges["length"]):
        names = name if isinstance(name, list) else [name]
        for n in names:
            n = _s(n)
            if n and (n not in best or length > best[n][0]):
                best[n] = (length, geom)
    out = []
    for n, (_, geom) in best.items():
        p = geom.interpolate(0.5, normalized=True)
        out.append({"id": f"ulica/{n}", "type": "ulica", "street": n, "number": None, "city": None,
                    "postcode": None, "lon": round(p.x, 6), "lat": round(p.y, 6)})
    return out


def main() -> None:
    cfg = load_config()
    raw = raw_dir(cfg)
    ox.settings.use_cache = True
    addresses = fetch_addresses(cfg)
    streets = streets_from_graph(raw)
    data = {"generated_at": date.today().isoformat(), "source": "OpenStreetMap contributors",
            "license": "ODbL 1.0", "source_url": "https://www.openstreetmap.org/copyright",
            "entries": addresses + streets}
    (raw / "addresses.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    print(f"zapisano raw/addresses.json: {len(addresses)} adresow, {len(streets)} ulic")


if __name__ == "__main__":
    main()
