"""API "Kraków bez barier" (FastAPI) - cienka warstwa na silniku (engine/) i danych (public/data/).
Zmienne srodowiskowe:
    HACKYEAH_SEED=1   wstaw kilka PRZYKLADOWYCH zgloszen (oznaczone "dane demo") - do pokazu sprzecznosci danych
    HACKYEAH_DEV=0    wylacz endpointy deweloperskie (/api/dev/*) na wdrozeniu

"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.profiles import PROFILES
from engine.routing import Net
from engine.geocode import Geocoder
from engine.realtime import Realtime
from engine.transit import Transit
from pipeline.common import ROOT, inside_aoi, load_aoi, load_config, out_dir

# atrybuty pokazywane na karcie miejsca per profil (klucze = tagi OSM z config.yaml)
PROFILE_ATTRS = {
    "wozek_inwalidzki": ["wheelchair", "wheelchair:description", "door:width", "entrance", "toilets:wheelchair"],
    "wozek_dziecko": ["wheelchair", "door:width", "entrance", "changing_table", "toilets:wheelchair"],
    "niewidomy_slabowidzacy": ["tactile_paving", "lit", "entrance"],
    "gluchy_niedoslyszacy": ["hearing_loop"],
    "senior": ["wheelchair", "entrance", "bench", "toilets:wheelchair"],
    "ciaza": ["wheelchair", "entrance", "toilets:wheelchair", "changing_table"],
}
DEFAULT_ATTRS = ["wheelchair", "wheelchair:description", "door:width", "entrance", "toilets:wheelchair",
                 "changing_table", "hearing_loop", "tactile_paving"]
ATTR_LABELS = {
    "wheelchair": "Dostęp dla wózka", "wheelchair:description": "Opis dostępności",
    "door:width": "Szerokość wejścia", "entrance": "Rodzaj wejścia", "toilets:wheelchair": "Toaleta dostępna dla wózka",
    "changing_table": "Przewijak", "hearing_loop": "Pętla indukcyjna", "tactile_paving": "Prowadzenie dotykowe",
    "lit": "Oświetlenie", "bench": "Ławka / miejsce odpoczynku",
}
VALUE_TEXT = {"yes": "tak", "no": "nie", "limited": "ograniczony", "designated": "przystosowany"}
ALLOWED_REPORT_ATTRS = set(ATTR_LABELS)
ATTRIBUTION = [
    "Dane mapy i obiektów: © OpenStreetMap contributors, licencja ODbL",
    "Model terenu (nachylenia): GUGiK / Geoportal (NMT), dane publiczne",
    "Rozkłady jazdy i dane na żywo: ZTP Kraków (GTFS) - rozkład, nie gwarancja; warunki licencji do potwierdzenia",
    "Zgłoszenia użytkowników: niezweryfikowane, oznaczone osobno",
]


def norm(s: str) -> str:
    s = (s or "").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def dist_m(a, b) -> float:
    import math
    dx = (a[0] - b[0]) * 111_320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110_540
    return math.hypot(dx, dy)


class Report(BaseModel):
    feature_id: str = Field(..., max_length=64, examples=["node/123456"])
    attribute: str = Field(..., max_length=64, examples=["wheelchair"])
    value: str = Field(..., max_length=100, examples=["no"])
    comment: str | None = Field(None, max_length=500)


class Outage(BaseModel):
    on: bool


class Store:
    def __init__(self, net: Net, pois_geojson: dict, facts: list, cfg: dict, reports_path: Path):
        self.net, self.cfg, self.reports_path = net, cfg, reports_path
        self.places: dict = {}
        for f in pois_geojson.get("features", []):
            p = f.get("properties", {})
            fid = p.get("feature_id")
            geom = f.get("geometry") or {}
            if not fid or geom.get("type") != "Point":
                continue
            cat = next((p[k] for k in ("amenity", "shop", "tourism", "leisure") if p.get(k)), None)
            self.places[fid] = {"id": fid, "name": p.get("name"), "category": cat,
                                "lon": geom["coordinates"][0], "lat": geom["coordinates"][1], "norm": norm(p.get("name") or "")}
        self.facts: dict = {}
        for r in facts:
            self.facts.setdefault(r["feature_id"], {}).setdefault(r["attribute"], []).append(r)
        self.reports: list = json.loads(reports_path.read_text("utf-8")) if reports_path.exists() else []
        self.outage = False
        self._barriers: dict = {}
        self.hits: dict = {}

    # ---- zgloszenia ----
    def save_reports(self):
        self.reports_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_path.write_text(json.dumps(self.reports, ensure_ascii=False, indent=1), "utf-8")

    def rate_ok(self, ip: str, limit: int = 10, window: int = 3600) -> bool:
        now = time.time()
        lst = [t for t in self.hits.get(ip, []) if now - t < window]
        ok = len(lst) < limit
        if ok:
            lst.append(now)
        self.hits[ip] = lst
        return ok

    def seed_demo_reports(self):
        if any(r.get("demo") for r in self.reports):
            return
        named = [fid for fid, p in self.places.items() if p["name"]]
        yes = next((fid for fid in named if any(f["value"] == "yes" for f in self.facts.get(fid, {}).get("wheelchair", []))), None)
        none = next((fid for fid in named if "wheelchair" not in self.facts.get(fid, {})), None)
        now = datetime.now(timezone.utc).isoformat()
        if yes:   # sprzecznosc: OSM mowi "tak", zgloszenie mowi "nie"
            self.reports.append({"id": uuid.uuid4().hex[:8], "feature_id": yes, "attribute": "wheelchair", "value": "no",
                                 "comment": "Przy wejściu są stopnie (PRZYKŁADOWE zgłoszenie - dane demo)",
                                 "created_at": now, "demo": True})
        if none:  # tylko zgloszenie, bez danych w OSM
            self.reports.append({"id": uuid.uuid4().hex[:8], "feature_id": none, "attribute": "wheelchair", "value": "limited",
                                 "comment": "Wąskie drzwi (PRZYKŁADOWE zgłoszenie - dane demo)", "created_at": now, "demo": True})
        self.save_reports()

    # ---- karta miejsca ----
    def attr_row(self, fid: str, attr: str) -> dict:
        base = {"attribute": attr, "label": ATTR_LABELS.get(attr, attr)}
        versions = []
        for f in self.facts.get(fid, {}).get(attr, []):
            versions.append({"value": f["value"], "source": f["source"], "source_url": f.get("source_url"),
                             "license": f.get("license"), "observed_at": f.get("observed_at"),
                             "retrieved_at": f.get("retrieved_at"), "confidence": f.get("confidence"), "status": f["status"],
                             "observed_basis": f.get("observed_basis"), "last_edit_at": f.get("last_edit_at")})
        for r in self.reports:
            if r["feature_id"] == fid and r["attribute"] == attr:
                src = "zgłoszenie użytkownika" + (" (PRZYKŁADOWE - dane demo)" if r.get("demo") else "")
                versions.append({"value": r["value"], "source": src, "source_url": None, "license": None,
                                 "observed_at": r["created_at"][:10], "retrieved_at": r["created_at"][:10],
                                 "confidence": 0.3, "status": "niezweryfikowane", "comment": r.get("comment")})
        if not versions:
            return {**base, "status": "brak", "value": None, "value_text": "brak danych", "confidence": 0.0,
                    "versions": [], "note": "Brak informacji nie oznacza, że miejsce jest dostępne."}
        if len({v["value"] for v in versions}) > 1:
            return {**base, "status": "sprzeczne", "value": None, "value_text": "sprzeczne informacje", "confidence": 0.0,
                    "versions": versions, "note": "Źródła podają różne wartości - sprawdź przed wizytą."}
        best = max(versions, key=lambda v: v.get("confidence") or 0)
        note = None
        if best.get("observed_basis") == "last_edit":
            note = ("Data to ostatnia edycja obiektu w OpenStreetMap, a nie potwierdzenie dostępności - "
                    "ktoś mógł zmienić np. nazwę, nie sprawdzając wejścia.")
        return {**base, "status": best["status"], "value": best["value"],
                "value_text": VALUE_TEXT.get(best["value"], best["value"]), "confidence": best.get("confidence"),
                "source": best["source"], "source_url": best.get("source_url"), "license": best.get("license"),
                "observed_at": best.get("observed_at"), "retrieved_at": best.get("retrieved_at"),
                "observed_basis": best.get("observed_basis"), "last_edit_at": best.get("last_edit_at"),
                "versions": versions, "note": note}

    def card(self, fid: str, profile: str | None) -> dict:
        p = self.places.get(fid)
        if not p:
            raise HTTPException(404, detail="Nie znaleziono miejsca")
        attrs = PROFILE_ATTRS.get(profile, DEFAULT_ATTRS) if profile else DEFAULT_ATTRS
        rows = [self.attr_row(fid, a) for a in attrs]
        missing = [r["label"] for r in rows if r["status"] == "brak"]
        wc = next((r for r in rows if r["attribute"] == "wheelchair"), None)
        if all(r["status"] == "brak" for r in rows):
            summary = {"level": "brak", "text": "Brak danych o dostępności. Nie zakładamy, że miejsce jest dostępne."}
        elif any(r["status"] == "sprzeczne" for r in rows):
            summary = {"level": "sprzeczne", "text": "Źródła podają sprzeczne informacje. Sprawdź przed wizytą."}
        elif wc and wc["value"] in ("yes", "designated"):
            extra = f" Brak szczegółów: {', '.join(missing)}." if missing else ""
            summary = {"level": "zadeklarowane", "text": f"Oznaczone jako dostępne ({wc['status']}), bez gwarancji.{extra}"}
        elif wc and wc["value"] == "limited":
            summary = {"level": "ograniczone", "text": "Dostęp ograniczony - zobacz szczegóły poniżej."}
        elif wc and wc["value"] == "no":
            summary = {"level": "niedostepne", "text": "Oznaczone jako niedostępne dla wózków."}
        else:
            summary = {"level": "czesciowe", "text": "Dostępne są tylko częściowe informacje."}
        banner = None
        if self.outage:
            when = max((f["retrieved_at"] for fs in self.facts.values() for l in fs.values() for f in l), default="?")
            banner = f"Źródło OpenStreetMap chwilowo niedostępne - pokazujemy dane zapisane {when}. Mogą być nieaktualne."
        return {"place": {k: p[k] for k in ("id", "name", "category", "lon", "lat")},
                "profile": PROFILES[profile]["label"] if profile in PROFILES else None,
                "summary": summary, "attributes": rows, "banner": banner}


def parse_profiles(s: str) -> list:
    keys = [k.strip() for k in (s or "").split(",") if k.strip()]
    bad = [k for k in keys if k not in PROFILES]
    if bad:
        raise HTTPException(422, detail=f"Nieznany profil: {bad}. Dostępne: {list(PROFILES)}")
    return keys


def create_app(net: Net | None = None, pois_geojson: dict | None = None, facts: list | None = None,
               cfg: dict | None = None, reports_path: Path | None = None, transit: Transit | None = None,
               realtime: Realtime | None = None, geocoder: Geocoder | None = None) -> FastAPI:
    cfg = cfg or load_config()
    out = out_dir(cfg)
    if transit is None:
        from pipeline.common import raw_dir
        transit = Transit.from_file(raw_dir(cfg) / "transit.json")
    realtime = realtime or Realtime()
    if geocoder is None:
        from pipeline.common import raw_dir as _raw
        geocoder = Geocoder.from_file(_raw(cfg) / "addresses.json")

    def add_live(block: dict, only_acc: bool) -> dict:
        """Dokleja do kazdego przystanku odjazdy na zywo (GTFS-RT). Awaria ZTP nie psuje reszty odpowiedzi."""
        for st in block["stops"]:
            full = transit.stops.get(st["id"])
            try:
                st["live"] = realtime.live_for_stop(full, transit.trips, only_accessible=only_acc) if full else \
                    {"available": False, "departures": []}
            except Exception:
                st["live"] = {"available": False, "reason": "Dane na żywo chwilowo niedostępne.", "departures": []}
        return block
    net = net or Net.from_files(cfg)
    if pois_geojson is None:
        pois_geojson = json.loads((out / "pois.geojson").read_text("utf-8"))
    if facts is None:
        facts = json.loads((out / "facts.json").read_text("utf-8"))
    store = Store(net, pois_geojson, facts, cfg, reports_path or (ROOT / "data" / "reports.json"))
    if os.getenv("HACKYEAH_SEED") == "1":
        store.seed_demo_reports()
    dev = os.getenv("HACKYEAH_DEV", "1") == "1"
    b = cfg["bbox"]

    def inside(lon, lat):
        return inside_aoi(cfg, lon, lat)

    def resolve(lon, lat, place, name):
        if place:
            p = store.places.get(place)
            if not p:
                raise HTTPException(404, detail=f"Nie znaleziono miejsca ({name}): {place}")
            return (p["lon"], p["lat"])
        if lon is None or lat is None:
            raise HTTPException(422, detail=f"Podaj {name}_lon i {name}_lat albo {name}_place")
        if not inside(lon, lat):
            raise HTTPException(422, detail=f"Punkt ({name}) poza obszarem demo")
        return (lon, lat)

    def resolve_q(q, lon, lat, place, name):
        """Punkt z adresu (q), miejsca (place) albo wspolrzednych. Zwraca (punkt, rozpoznana_etykieta)."""
        if q:
            if not geocoder.available:
                raise HTTPException(503, detail="Geokodowanie niedostępne (uruchom pipeline.fetch_addresses)")
            hits = geocoder.search(q, 1)
            if not hits:
                raise HTTPException(404, detail=f"Nie znaleziono adresu ({name}): {q}")
            return (hits[0]["lon"], hits[0]["lat"]), hits[0]["label"]
        return resolve(lon, lat, place, name), None

    app = FastAPI(title="Kraków bez barier - API", version="0.1",
                  description="Trasy i karty miejsc dopasowane do potrzeb. Brak danych nie oznacza dostępności.")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/meta")
    def meta():
        dates = [f["retrieved_at"] for fs in store.facts.values() for l in fs.values() for f in l]
        return {"bbox": b, "profiles": [{"key": k, "label": v["label"], "needs": v["needs"]} for k, v in PROFILES.items()],
                "modes": {"warn": "ostrzegaj o niepewnych danych", "strict": "tylko pewne"},
                "dane_pobrane": max(dates) if dates else None, "miejsc": len(store.places),
                "zgloszen": len(store.reports), "transport": transit.available, "lawki_w_danych": store.net.rest_count, "geokodowanie": geocoder.available, "zrodlo_niedostepne": store.outage, "atrybucja": ATTRIBUTION,
                "uwaga": "Brak danych nie oznacza dostępności. Zgłoszenia użytkowników są niezweryfikowane."}

    @app.get("/api/area")
    def area():
        """Obrys obszaru demo (GeoJSON, WGS84) - do narysowania na mapie i ustawienia widoku."""
        import shapely
        from shapely.geometry import mapping
        return {"type": "Feature", "properties": {"name": "Obszar demo", "bbox": b},
                "geometry": mapping(shapely.set_precision(load_aoi(cfg), 1e-6))}

    @app.get("/api/sources")
    def sources():
        """Rejestr zrodel danych (brief pkt 7): pochodzenie, licencja, aktualnosc, sposob weryfikacji."""
        import yaml
        from pipeline.common import raw_dir as _raw
        reg = yaml.safe_load((ROOT / "sources.yaml").read_text("utf-8"))
        raw = _raw(cfg)

        def mtime(name):
            f = raw / name
            return datetime.fromtimestamp(f.stat().st_mtime).date().isoformat() if f.exists() else None

        def json_field(name, key):
            f = raw / name
            try:
                return json.loads(f.read_text("utf-8")).get(key)
            except Exception:
                return None

        fresh = {"facts": max((f["retrieved_at"] for fs in store.facts.values() for l in fs.values() for f in l), default=None),
                 "osm_meta": json_field("osm_meta.json", "fetched_at"),
                 "dem": mtime("edges_incline.pkl"),
                 "transit": transit.meta.get("generated_at")}
        for s_ in reg["used"]:
            key = s_.pop("retrieved_from_file", None)
            s_["data_retrieved_at"] = fresh.get(key) if key else None
        return {"used": reg["used"], "considered_not_used": reg["considered_not_used"],
                "rule": "Brak danych nie oznacza dostępności. Zgłoszenia użytkowników są niezweryfikowane."}

    @app.get("/api/geocode")
    def geocode(q: str = Query(..., min_length=2, max_length=100), limit: int = Query(8, ge=1, le=20)):
        """Adres/ulica/miejsce -> wspolrzedne (do pol 'skad/dokad' zamiast klikania w mape). Dziala na danych lokalnych."""
        if not geocoder.available:
            raise HTTPException(503, detail="Geokodowanie niedostępne (uruchom pipeline.fetch_addresses)")
        res = geocoder.search(q, limit)
        qn = norm(q)
        if len(res) < limit:   # nazwy miejsc (kawiarnie, muzea...) z tych samych danych OSM
            for p in sorted((p for p in store.places.values() if p["norm"] and qn in p["norm"]),
                            key=lambda p: (not p["norm"].startswith(qn), len(p["norm"])))[: limit - len(res)]:
                res.append({"id": p["id"], "label": p["name"], "type": "miejsce", "street": None, "number": None,
                            "lon": p["lon"], "lat": p["lat"], "exact": False, "approximate": False, "fuzzy": False})
        return {"results": res, "source": geocoder.meta.get("source"), "license": geocoder.meta.get("license"),
                "note": "Tylko adresy zapisane w OpenStreetMap w obszarze demo. Brak wyniku nie oznacza, że adres nie istnieje."}

    @app.get("/api/places")
    def places(q: str = Query(..., min_length=2, max_length=60), limit: int = Query(10, ge=1, le=30)):
        qn = norm(q)
        hits = [p for p in store.places.values() if p["norm"] and qn in p["norm"]]
        hits.sort(key=lambda p: (not p["norm"].startswith(qn), len(p["norm"])))
        return [{k: p[k] for k in ("id", "name", "category", "lon", "lat")} for p in hits[:limit]]

    @app.get("/api/places/{feature_id:path}")
    def place_card(feature_id: str, profile: str | None = None):
        if profile and profile not in PROFILES:
            raise HTTPException(422, detail=f"Nieznany profil: {profile}")
        card = store.card(feature_id, profile)
        if transit.available:
            pl = card["place"]
            acc = profile in ("wozek_inwalidzki", "wozek_dziecko")
            card["transit"] = add_live(transit.nearby_with_departures(
                pl["lon"], pl["lat"], datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None),
                only_accessible=acc), acc)
        return card

    @app.get("/api/transit/nearby")
    def transit_nearby(lon: float, lat: float, radius: int = Query(400, ge=50, le=1000), n: int = Query(3, ge=1, le=10),
                       only_accessible: bool = False):
        if not transit.available:
            raise HTTPException(503, detail="Brak danych o komunikacji (uruchom pipeline.fetch_gtfs)")
        if not inside(lon, lat):
            raise HTTPException(422, detail="Punkt poza obszarem demo")
        return add_live(transit.nearby_with_departures(
            lon, lat, datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None),
            radius_m=radius, n=n, only_accessible=only_accessible), only_accessible)

    @app.get("/api/route")
    def route(from_lon: float | None = None, from_lat: float | None = None, from_place: str | None = None,
              to_lon: float | None = None, to_lat: float | None = None, to_place: str | None = None,
              from_q: str | None = Query(None, max_length=100), to_q: str | None = Query(None, max_length=100),
              profiles: str = "", mode: str = Query("warn", pattern="^(warn|strict)$")):
        keys = parse_profiles(profiles)
        (a, a_label), (z, z_label) = (resolve_q(from_q, from_lon, from_lat, from_place, "from"),
                                      resolve_q(to_q, to_lon, to_lat, to_place, "to"))
        r = store.net.route(a, z, keys, mode)
        if r is None:
            raise HTTPException(404, detail={"message": "Nie znaleziono trasy dla tego profilu.",
                                             "hint": "W trybie 'strict' trasa może nie istnieć przy brakach danych. Spróbuj mode=warn."})
        warnings = []
        for q_, lab in ((from_q, a_label), (to_q, z_label)):
            if q_ and lab:
                warnings.append(f"Adres „{q_}” rozpoznano jako: {lab}.")
        if dist_m(a, r["coords"][0]) > 150 or dist_m(z, r["coords"][-1]) > 150:
            warnings.append("Punkt startu lub celu jest daleko od sieci pieszej - trasa zaczyna się w najbliższym dostępnym miejscu.")
        if r["pct_niepewne"] > 0:
            warnings.append(f"{r['pct_niepewne']}% trasy ma niepełne dane - patrz kroki oznaczone UWAGA.")
        if store.outage:
            warnings.append("Źródło OpenStreetMap chwilowo niedostępne - dane z zapisu, mogą być nieaktualne.")
        props = {k: r[k] for k in ("profile", "mode", "length_m", "time_min", "pct_niepewne", "steps", "max_do_lawki_m", "lawki_w_danych")}
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": r["coords"]},
                "properties": {**props, "start_label": a_label, "end_label": z_label, "warnings": warnings,
                               "atrybucja": ATTRIBUTION}}

    @app.get("/api/isochrone")
    def isochrone(lon: float, lat: float, profiles: str = "", minutes: float = Query(15, ge=1, le=30),
                  mode: str = Query("warn", pattern="^(warn|strict)$")):
        keys = parse_profiles(profiles)
        if not inside(lon, lat):
            raise HTTPException(422, detail="Punkt poza obszarem demo")
        iso = store.net.isochrone((lon, lat), keys, minutes, mode)
        if iso is None:
            raise HTTPException(404, detail="Nie udało się wyznaczyć obszaru z tego punktu")
        geom = iso.pop("geometry")
        return {"type": "Feature", "geometry": geom, "properties": iso}

    @app.get("/api/barriers")
    def barriers(profile: str, top: int = Query(15, ge=1, le=50), mode: str = Query("warn", pattern="^(warn|strict)$")):
        parse_profiles(profile)
        ck = (profile, mode)
        if ck not in store._barriers:
            store._barriers[ck] = store.net.barrier_ranking([profile], top=50, mode=mode)
        return store._barriers[ck][:top]

    @app.post("/api/reports", status_code=201)
    def add_report(rep: Report, request: Request):
        ip = request.client.host if request.client else "?"
        if not store.rate_ok(ip):
            raise HTTPException(429, detail="Za dużo zgłoszeń. Spróbuj później.")
        if rep.feature_id not in store.places:
            raise HTTPException(404, detail="Nie znaleziono miejsca")
        if rep.attribute not in ALLOWED_REPORT_ATTRS:
            raise HTTPException(422, detail=f"Niedozwolony atrybut. Dozwolone: {sorted(ALLOWED_REPORT_ATTRS)}")
        clean = lambda s: re.sub(r"[\x00-\x1f<>]", "", re.sub(r"<[^>]*>", "", s or "")).strip()
        r = {"id": uuid.uuid4().hex[:8], "feature_id": rep.feature_id, "attribute": rep.attribute,
             "value": clean(rep.value), "comment": clean(rep.comment) or None,
             "created_at": datetime.now(timezone.utc).isoformat(), "demo": False}
        store.reports.append(r)
        store.save_reports()
        return {"id": r["id"], "status": "niezweryfikowane",
                "message": "Dziękujemy. Zgłoszenie jest widoczne jako niezweryfikowane do czasu potwierdzenia."}

    if dev:
        @app.post("/api/dev/outage")
        def set_outage(o: Outage):
            """Symulacja niedostepnosci zrodla danych (do pokazu w demo)."""
            store.outage = o.on
            return {"zrodlo_niedostepne": store.outage}

        @app.post("/api/dev/seed")
        def seed():
            store.seed_demo_reports()
            return {"zgloszen": len(store.reports)}

    return app
