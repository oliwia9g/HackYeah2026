"""Obrysy budynkow: klik w mape (wspolrzedne) -> budynek -> jego adres.

Dane: buildings.geojson z pipeline.fetch_osm (wielokaty z OSM). Adres budynku bierzemy w kolejnosci:
  1. tagi adresowe samego budynku (addr:street + addr:housenumber),
  2. punkt adresowy lezacy wewnatrz obrysu (osobny wezel adresowy w OSM),
  3. (poza tym modulem) najblizszy adres w pobliżu — oznaczony jako przyblizony.
Nic nie zgadujemy: gdy adresu nie ma, mowimy to wprost.
"""
from __future__ import annotations

import math

from shapely import STRtree
from shapely.geometry import Point, shape


class Buildings:
    def __init__(self, geojson: dict | None):
        self.items: list[dict] = []
        geoms = []
        for f in (geojson or {}).get("features", []):
            p = f.get("properties") or {}
            fid = p.get("feature_id")
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            if not fid or g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            street = p.get("addr:street") or p.get("addr:place")
            self.items.append({"id": fid, "building": p.get("building"), "name": p.get("name"), "street": street,
                               "number": p.get("addr:housenumber"), "city": p.get("addr:city"), "geom": g,
                               "centroid": g.representative_point()})
            geoms.append(g)
        self._tree = STRtree(geoms) if geoms else None

    @property
    def available(self) -> bool:
        return bool(self.items)

    def at(self, lon: float, lat: float, snap_m: float = 10.0) -> tuple[dict | None, float]:
        """Budynek zawierajacy punkt; gdy klik trafil tuz obok obrysu (do snap_m metrow) - najblizszy budynek. Zwraca (budynek, odleglosc_m)."""
        if not self._tree:
            return None, 0.0
        pt = Point(lon, lat)
        for i in self._tree.query(pt, predicate="intersects"):
            return self.items[int(i)], 0.0
        kx, ky = 111_320 * math.cos(math.radians(lat)), 110_540
        r = snap_m / min(kx, ky) * 1.5
        best = None
        for i in self._tree.query(pt.buffer(r)):
            it = self.items[int(i)]
            near = it["geom"].exterior.interpolate(it["geom"].exterior.project(pt)) if it["geom"].geom_type == "Polygon" \
                else min((pg.exterior.interpolate(pg.exterior.project(pt)) for pg in it["geom"].geoms), key=lambda q: q.distance(pt))
            d = math.hypot((near.x - lon) * kx, (near.y - lat) * ky)
            if d <= snap_m and (best is None or d < best[1]):
                best = (it, d)
        return best if best else (None, 0.0)

    def by_id(self, fid: str) -> dict | None:
        return next((it for it in self.items if it["id"] == fid), None)

    @staticmethod
    def label(b: dict) -> str | None:
        if b.get("street") and b.get("number"):
            return f"{b['street']} {b['number']}" + (f", {b['city']}" if b.get("city") else "")
        return None
