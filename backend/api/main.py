from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.profiles import PROFILES
from engine.routing import Net
from pipeline.common import ROOT, load_config, out_dir

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
                             "retrieved_at": f.get("retrieved_at"), "confidence": f.get("confidence"), "status": f["status"]})
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
        return {**base, "status": best["status"], "value": best["value"],
                "value_text": VALUE_TEXT.get(best["value"], best["value"]), "confidence": best.get("confidence"),
                "source": best["source"], "source_url": best.get("source_url"), "license": best.get("license"),
                "observed_at": best.get("observed_at"), "retrieved_at": best.get("retrieved_at"),
                "versions": versions, "note": None}

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
               cfg: dict | None = None, reports_path: Path | None = None) -> FastAPI:
    cfg = cfg or load_config()
    out = out_dir(cfg)
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
        return b["west"] <= lon <= b["east"] and b["south"] <= lat <= b["north"]

    def resolve(lon, lat, place, name):
        if place:
            p = store.places.get(place)
            if not p:
                raise HTTPException(404, detail=f"Nie znaleziono miejsca ({name}): {place}")
            return (p["lon"], p["lat"])
        if lon is None or lat is None:
            raise HTTPException(422, detail=f"Podaj {name}_lon i {name}_lat albo {name}_place")
        if not inside(lon, lat):
            raise HTTPException(422, detail=f"Punkt ({name}) poza obszarem demo (Stare Miasto, Kazimierz, Dworzec)")
        return (lon, lat)

    app = FastAPI(title="Kraków bez barier - API", version="0.1",
                  description="Trasy i karty miejsc dopasowane do potrzeb. Brak danych nie oznacza dostępności.")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/meta")
    def meta():
        dates = [f["retrieved_at"] for fs in store.facts.values() for l in fs.values() for f in l]
        return {"bbox": b, "profiles": [{"key": k, "label": v["label"], "needs": v["needs"]} for k, v in PROFILES.items()],
                "modes": {"warn": "ostrzegaj o niepewnych danych", "strict": "tylko pewne"},
                "dane_pobrane": max(dates) if dates else None, "miejsc": len(store.places),
                "zgloszen": len(store.reports), "zrodlo_niedostepne": store.outage, "atrybucja": ATTRIBUTION,
                "uwaga": "Brak danych nie oznacza dostępności. Zgłoszenia użytkowników są niezweryfikowane."}

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
        return store.card(feature_id, profile)

    @app.get("/api/route")
    def route(from_lon: float | None = None, from_lat: float | None = None, from_place: str | None = None,
              to_lon: float | None = None, to_lat: float | None = None, to_place: str | None = None,
              profiles: str = "", mode: str = Query("warn", pattern="^(warn|strict)$")):
        keys = parse_profiles(profiles)
        a, z = resolve(from_lon, from_lat, from_place, "from"), resolve(to_lon, to_lat, to_place, "to")
        r = store.net.route(a, z, keys, mode)
        if r is None:
            raise HTTPException(404, detail={"message": "Nie znaleziono trasy dla tego profilu.",
                                             "hint": "W trybie 'strict' trasa może nie istnieć przy brakach danych. Spróbuj mode=warn."})
        warnings = []
        if dist_m(a, r["coords"][0]) > 150 or dist_m(z, r["coords"][-1]) > 150:
            warnings.append("Punkt startu lub celu jest daleko od sieci pieszej - trasa zaczyna się w najbliższym dostępnym miejscu.")
        if r["pct_niepewne"] > 0:
            warnings.append(f"{r['pct_niepewne']}% trasy ma niepełne dane - patrz kroki oznaczone UWAGA.")
        if store.outage:
            warnings.append("Źródło OpenStreetMap chwilowo niedostępne - dane z zapisu, mogą być nieaktualne.")
        props = {k: r[k] for k in ("profile", "mode", "length_m", "time_min", "pct_niepewne", "steps")}
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": r["coords"]},
                "properties": {**props, "warnings": warnings, "atrybucja": ATTRIBUTION}}

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
