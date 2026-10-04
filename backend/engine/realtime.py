"""Dane na zywo z ZTP Krakow (GTFS-Realtime): najblizsze przyjazdy + dostepnosc pojazdu.

- TripUpdates_{T,A}.pb      -> prognozowane przyjazdy na przystanki
- VehiclePositions_{T,A}.pb -> pojazd (numer, flaga wheelchair_accessible), laczone po trip_id

Zasady: flaga dostepnosci pochodzi od operatora i dotyczy POJAZDU, ktory teraz obsluguje kurs
(moze sie zmienic). Brak flagi = "brak danych", nigdy "dostepne". Gdy ZTP nie odpowiada,
zwracamy ostatnie dane z cache oznaczone jako nieswieze, a gdy nie ma nic - jawny komunikat.
"""
from __future__ import annotations

import time
from datetime import datetime

import requests
from zoneinfo import ZoneInfo

from engine.fleet import OK, vehicle_access

TZ = ZoneInfo("Europe/Warsaw")
BASE = "https://gtfs.ztp.krakow.pl/"
FEEDS = {"tramwaj": "T", "autobus": "A"}      # etykieta z fetch_gtfs -> przyrostek pliku
TTL = 20          # sekund - tyle trzymamy odpowiedz ZTP w pamieci
STALE_MAX = 600   # po tylu sekundach bez odswiezenia nie pokazujemy juz danych "na zywo"
HEADERS = {"User-Agent": "HackYeah2026-krakow-bez-barier/0.1 (hackathon prototype)"}
WC = {2: "yes", 3: "no"}   # VehicleDescriptor.WheelchairAccessible: 2 = ACCESSIBLE, 3 = INACCESSIBLE; reszta = brak danych
WC_TEXT = {"yes": "pojazd oznaczony przez ZTP jako dostępny", "no": "pojazd oznaczony jako niedostępny",
           "unknown": "brak danych o dostępności pojazdu"}
NOTE = ("Dane na żywo z ZTP (prognoza przyjazdu). Dostępność dotyczy pojazdu obsługującego kurs w tej chwili "
        "i może się zmienić; brak informacji nie oznacza dostępności.")


def _make_fetcher(base: str):
    def fetch(name: str) -> bytes:
        r = requests.get(base + name, headers=HEADERS, timeout=6)
        r.raise_for_status()
        return r.content
    return fetch


class Realtime:
    def __init__(self, fetcher=None, base: str | None = None):
        """base: adres katalogu z plikami GTFS-RT (domyslnie ZTP Krakow; w config.yaml: transit.realtime_base)."""
        self.base = base or BASE
        self._fetch = fetcher or _make_fetcher(self.base)
        self._cache: dict = {}          # label -> {"at": ts, "arrivals": {...}, "vehicles": {...}}

    def _load(self, label: str) -> dict | None:
        from google.transit import gtfs_realtime_pb2 as rt
        suffix = FEEDS[label]
        c = self._cache.get(label)
        if c and time.time() - c["at"] < TTL:
            return c
        tu, vp = rt.FeedMessage(), rt.FeedMessage()
        for attempt in (1, 2):   # ZTP czasem zwraca plik uciety w trakcie zapisu - jedno ponowienie wystarcza
            try:
                tu.Clear()
                vp.Clear()
                tu.ParseFromString(self._fetch(f"TripUpdates_{suffix}.pb"))
                vp.ParseFromString(self._fetch(f"VehiclePositions_{suffix}.pb"))
                break
            except Exception:   # siec, 5xx, uszkodzony plik
                if attempt == 2:   # wracamy do cache, jesli nie jest za stary
                    return c if c and time.time() - c["at"] < STALE_MAX else None
                time.sleep(0.5)
        vehicles = {}
        for e in vp.entity:
            v = e.vehicle
            if v.trip.trip_id:
                vehicles[v.trip.trip_id] = {"label": v.vehicle.label or v.vehicle.id,
                                            "wheelchair": WC.get(v.vehicle.wheelchair_accessible, "unknown")}
        arrivals: dict = {}      # stop_id -> [(czas_unix, trip_id, opoznienie_s)]
        for e in tu.entity:
            t = e.trip_update
            for u in t.stop_time_update:
                ev = u.arrival if u.HasField("arrival") and u.arrival.time else u.departure
                if ev.time:
                    arrivals.setdefault(u.stop_id, []).append((int(ev.time), t.trip.trip_id, ev.delay if ev.HasField("delay") else None))
        c = {"at": time.time(), "arrivals": arrivals, "vehicles": vehicles}
        self._cache[label] = c
        return c

    def status(self) -> dict:
        """Stan danych na zywo (do /api/health): czy ZTP odpowiada i jak stare sa dane z cache."""
        out = {}
        for label in FEEDS:
            try:
                c = self._load(label)
            except Exception:
                c = None
            out[label] = {"ok": c is not None, "age_s": round(time.time() - c["at"]) if c else None,
                          "pojazdow": len(c["vehicles"]) if c else 0}
        return out

    def vehicle_for_trip(self, label: str, trip_id: str) -> dict | None:
        """Pojazd obslugujacy kurs w tej chwili ({label, wheelchair}) albo None (brak danych / ZTP niedostepne)."""
        if label not in FEEDS:
            return None
        try:
            c = self._load(label)
        except Exception:
            return None
        return c["vehicles"].get(trip_id) if c else None

    def live_for_stop(self, stop: dict, trips: dict, now_ts: float | None = None, n: int = 3,
                      only_accessible: bool = False) -> dict:
        """stop: wpis z transit.json (id "tramwaj:123", gtfs_id, feed)."""
        label = stop.get("feed")
        if label not in FEEDS:
            return {"available": False, "reason": "brak danych na żywo dla tego źródła", "departures": []}
        c = self._load(label)
        if c is None:
            return {"available": False, "reason": "Dane na żywo z ZTP są chwilowo niedostępne - pokazujemy tylko rozkład.",
                    "departures": []}
        now_ts = now_ts or time.time()
        stale = time.time() - c["at"] > TTL * 3
        rows = []
        for ts, trip_id, delay in sorted(c["arrivals"].get(stop["gtfs_id"], [])):
            if ts < now_ts - 30:
                continue
            veh = c["vehicles"].get(trip_id)
            acc = vehicle_access(stop.get("feed"), veh["wheelchair"] if veh else "unknown", veh["label"] if veh else None)
            if only_accessible and acc["wheelchair"] not in OK:
                continue
            line, head = trips.get(f"{label}:{trip_id}", [None, None])
            rows.append({"time": datetime.fromtimestamp(ts, TZ).strftime("%H:%M"), "in_min": max(0, int((ts - now_ts) // 60)),
                         "line": line, "headsign": head, "delay_s": delay, "vehicle": veh["label"] if veh else None,
                         **acc})
            if len(rows) >= n:
                break
        return {"available": True, "stale": stale, "updated_at": datetime.fromtimestamp(c["at"], TZ).strftime("%H:%M:%S"),
                "note": NOTE, "source": "ZTP Kraków GTFS-Realtime", "source_url": self.base, "departures": rows}
