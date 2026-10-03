"""Komunikacja miejska z rozkladu GTFS: przystanki w poblizu i najblizsze odjazdy.

Uwaga (zgodnie z zasadami projektu): to ROZKLAD JAZDY, nie pozycje pojazdow na zywo.
Brak informacji o niskiej podlodze = "brak danych", nigdy "dostepne".
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from engine.fleet import OK, vehicle_access

NOTE = "Dane z rozkładu jazdy ZTP, nie czas rzeczywisty. Kursy mogą się opóźnić lub zmienić."
WC_TEXT = {"yes": "niskopodłogowy / dostępny", "likely": "prawdopodobnie dostępny", "no": "niedostępny dla wózka",
           "unknown": "brak danych o dostępności"}


def _dist_m(lon1, lat1, lon2, lat2) -> float:
    dx = (lon1 - lon2) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, (lat1 - lat2) * 110_540)


class Transit:
    def __init__(self, data: dict | None):
        data = data or {}
        self.stops: dict = data.get("stops", {})
        self.services: dict = data.get("services", {})
        self.exceptions: dict = data.get("exceptions", {})
        self.trips: dict = data.get("trips", {})
        self.trip_keys: list = data.get("trip_keys", [])
        self.meta = {k: data.get(k) for k in ("generated_at", "source", "source_url", "license")}
        self.by_stop: dict = {}
        for d in data.get("departures", []):
            self.by_stop.setdefault(d[0], []).append(d)
        for lst in self.by_stop.values():
            lst.sort(key=lambda d: d[1])
        # kurs -> [(sekunda, przystanek)] tylko dla przystankow z obszaru demo (do planowania przejazdow)
        self.trip_stops: dict = {}
        for d in data.get("departures", []):
            if len(d) > 6:
                self.trip_stops.setdefault(d[6], []).append((d[1], d[0]))
        for lst in self.trip_stops.values():
            lst.sort()

    @classmethod
    def from_file(cls, path: Path) -> "Transit":
        path = Path(path)
        return cls(json.loads(path.read_text("utf-8")) if path.exists() else None)

    @property
    def has_accessibility_data(self) -> bool:
        """Czy feed w ogole cokolwiek mowi o dostepnosci (ZTP Krakow na razie: nie - same zera)."""
        if not hasattr(self, "_has_acc"):
            self._has_acc = any(s["wheelchair_boarding"] != "unknown" for s in self.stops.values()) or \
                any(d[4] != "unknown" for l in self.by_stop.values() for d in l)
        return self._has_acc

    @property
    def can_plan(self) -> bool:
        """Czy dane maja numery kursow (wymagane do laczenia przystankow w przejazd). Starsze transit.json: nie."""
        return bool(self.trip_stops)

    def rides(self, board_ids: set, alight_ids: set, earliest: datetime, horizon_min: int = 90, per_board: int = 4) -> list:
        """Przejazdy jednym kursem: wsiadamy na jednym z board_ids nie wczesniej niz `earliest`, wysiadamy na jednym z alight_ids.
        Zwraca liste dict (posortowana po godzinie przyjazdu na przystanek docelowy)."""
        out = []
        for b in board_ids:
            found = 0
            for offset in (-1, 0, 1):
                day = (earliest + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                for d in self.by_stop.get(b, []):
                    if len(d) < 7:
                        continue
                    dep = day + timedelta(seconds=d[1])
                    if dep < earliest or dep > earliest + timedelta(minutes=horizon_min) or not self._active(d[5], day):
                        continue
                    nxt = [(sec, sid) for sec, sid in self.trip_stops.get(d[6], []) if sid in alight_ids and sec > d[1]]
                    if not nxt:
                        continue
                    sec_a, alight = min(nxt)
                    out.append({"board": b, "alight": alight, "dep": dep, "arr": day + timedelta(seconds=sec_a),
                                "line": d[2], "headsign": d[3], "wc": d[4], "trip": d[6], "service": d[5],
                                "stops_between": sum(1 for sec, _ in self.trip_stops[d[6]] if d[1] < sec <= sec_a)})
                    found += 1
            out.sort(key=lambda r: r["arr"])
        out.sort(key=lambda r: r["arr"])
        return out

    @property
    def available(self) -> bool:
        return bool(self.stops)

    def _active(self, service_id: str, day: datetime) -> bool:
        ymd = day.strftime("%Y%m%d")
        exc = self.exceptions.get(service_id, {}).get(ymd)
        if exc == 1:
            return True
        if exc == 2:
            return False
        s = self.services.get(service_id)
        return bool(s and s["start"] <= ymd <= s["end"] and s["days"][day.weekday()])

    def nearby(self, lon: float, lat: float, radius_m: float = 400, limit: int = 8) -> list:
        res = []
        for s in self.stops.values():
            d = _dist_m(lon, lat, s["lon"], s["lat"])
            if d <= radius_m:
                res.append({**s, "distance_m": round(d)})
        res.sort(key=lambda s: s["distance_m"])
        return res[:limit]

    def departures(self, stop_id: str, now: datetime, n: int = 5, only_accessible: bool = False) -> list:
        """Najblizsze odjazdy po czasie `now` (czas lokalny). Obsluguje kursy po polnocy (czas > 24:00)."""
        out = []
        for offset in (-1, 0, 1):   # wczorajszy rozklad (kursy po polnocy), dzisiejszy, jutrzejszy
            day = (now + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            for d in self.by_stop.get(stop_id, []):
                sid, sec, line, head, wc, svc = d[:6]
                if stop_id.startswith("autobus:") and wc == "unknown":
                    wc = "likely"   # deklaracja MPK (wszystkie autobusy niskopodlogowe od 2018); nie "yes"
                if only_accessible and wc not in OK:
                    continue
                t = day + timedelta(seconds=sec)
                if t < now or not self._active(svc, day):
                    continue
                out.append((t, line, head, wc))
        out.sort(key=lambda x: x[0])
        return [{"time": t.strftime("%H:%M"), "date": t.strftime("%Y-%m-%d"), "in_min": max(0, int((t - now).total_seconds() // 60)),
                 "line": line, "headsign": head, "wheelchair": wc, "wheelchair_text": WC_TEXT[wc],
                 "wheelchair_basis": "deklaracja MPK Kraków (flota niskopodłogowa od 2018 r.), nie sprawdzenie pojazdu" if wc == "likely" else None}
                for t, line, head, wc in out[:n]]

    def nearby_with_departures(self, lon: float, lat: float, now: datetime, radius_m: float = 400,
                               limit: int = 4, n: int = 3, only_accessible: bool = False) -> dict:
        stops = []
        requested = only_accessible
        only_accessible = only_accessible and self.has_accessibility_data   # bez danych nie filtrujemy do pustej listy
        for s in self.nearby(lon, lat, radius_m, limit):
            stops.append({"id": s["id"], "name": s["name"], "mode": s["mode"], "lines": s["lines"],
                          "distance_m": s["distance_m"], "lon": s["lon"], "lat": s["lat"],
                          "wheelchair_boarding": s["wheelchair_boarding"],
                          "wheelchair_boarding_text": WC_TEXT[s["wheelchair_boarding"]],
                          "departures": self.departures(s["id"], now, n, only_accessible)})
        acc_note = None
        if not self.has_accessibility_data:
            acc_note = ("W rozkładzie jazdy ZTP nie ma informacji o niskiej podłodze ani o dostępności przystanków. "
                        "Autobusy: wg MPK Kraków od 2018 r. cała flota jest niskopodłogowa - oznaczamy je jako „prawdopodobnie dostępne” "
                        "(deklaracja przewoźnika, nie sprawdzenie pojazdu). Tramwaje: dostępność pojazdu pojawia się dopiero w danych na żywo (pole live). "
                        "Dostępność pojazdu to nie dostępność przystanku. Brak danych nie oznacza dostępności.")
        return {"stops": stops, "note": NOTE, "accessibility_note": acc_note, "accessibility_data_in_feed": self.has_accessibility_data, "source": self.meta.get("source"),
                "source_url": self.meta.get("source_url"), "license": self.meta.get("license"),
                "data_date": self.meta.get("generated_at"), "only_accessible": only_accessible,
                "only_accessible_requested": requested}
