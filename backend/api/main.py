"""API "Kraków bez barier" (FastAPI) - cienka warstwa na silniku (engine/) i danych (public/data/).

Uruchomienie (z katalogu backend/):
    pip install -r requirements.txt
    uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
    # dokumentacja i test w przegladarce:  http://localhost:8000/docs

Zmienne srodowiskowe:
    HACKYEAH_SEED=1   wstaw kilka PRZYKLADOWYCH zgloszen (oznaczone "dane demo") - do pokazu sprzecznosci danych
    HACKYEAH_DEV=0    wylacz endpointy deweloperskie (/api/dev/*) na wdrozeniu
    ADMIN_TOKEN=...   wlacza moderacje zgloszen (naglowek X-Admin-Token); bez niego /api/admin/* zwraca 404
    TRUST_PROXY=1     za reverse proxy: adres klienta (limit zgloszen) z X-Forwarded-For
    CITY_CONFIG=cities/xxx.yaml   inne miasto (domyslnie config.yaml = Krakow)
    DATA_RAW_DIR / DATA_OUT_DIR / REPORTS_PATH   katalogi danych i plik zgloszen na serwerze (wolumen)
    CORS_ORIGINS=https://front.example,https://inny.example   dozwolone domeny frontu (domyslnie *)

Zasady (z briefu): kazda informacja ma zrodlo, date i status; brak danych != dostepne;
zgloszenia uzytkownikow sa niezweryfikowane i wyraznie odroznione; bez kont i bez danych osobowych.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from engine.profiles import CATALOG, PROFILES, PREF_HELP, active_items, build_profile, catalog as profile_catalog, custom_profile, merge_profiles, profile_speed, resolve_selection
from engine.routing import Net, SPEED_KMH, as_set, kerb_info
from engine.voice import parse_command
from engine import localprofile
from engine.buildings import Buildings
from engine.multimodal import plan as plan_multimodal
from engine.geocode import Geocoder, deinflect
from engine.simple import simple_route, spoken_summary
from engine.surveys import OBS_TYPES, Surveys
from engine.realtime import Realtime
from engine.transit import Transit
from pipeline.common import ROOT, inside_aoi, load_aoi, load_config, out_dir

# atrybuty pokazywane na karcie miejsca per profil (klucze = tagi OSM z config.yaml)
PROFILE_ATTRS = {
    "wozek_inwalidzki": ["wheelchair", "wheelchair:description", "door:width", "entrance", "step_count", "ramp:wheelchair", "automatic_door",
                         "elevator", "toilets:wheelchair"],
    "wozek_dziecko": ["wheelchair", "door:width", "entrance", "step_count", "ramp:wheelchair", "elevator", "changing_table", "toilets:wheelchair"],
    "niewidomy_slabowidzacy": ["tactile_paving", "lit", "entrance", "handrail"],
    "gluchy_niedoslyszacy": ["hearing_loop"],
    "senior": ["wheelchair", "entrance", "step_count", "elevator", "handrail", "bench", "toilets:wheelchair"],
    "ciaza": ["wheelchair", "entrance", "step_count", "elevator", "toilets:wheelchair", "changing_table"],
}
DEFAULT_ATTRS = ["wheelchair", "wheelchair:description", "door:width", "entrance", "step_count", "ramp:wheelchair", "elevator",
                 "toilets:wheelchair", "changing_table", "hearing_loop", "tactile_paving"]
ATTR_LABELS = {
    "wheelchair": "Dostęp dla wózka", "wheelchair:description": "Opis dostępności",
    "door:width": "Szerokość wejścia", "entrance": "Rodzaj wejścia", "toilets:wheelchair": "Toaleta dostępna dla wózka",
    "changing_table": "Przewijak", "hearing_loop": "Pętla indukcyjna", "tactile_paving": "Prowadzenie dotykowe",
    "lit": "Oświetlenie", "bench": "Ławka / miejsce odpoczynku",
    "elevator": "Winda", "ramp:wheelchair": "Rampa dla wózka", "ramp": "Rampa", "step_count": "Liczba stopni przy wejściu",
    "automatic_door": "Drzwi automatyczne", "handrail": "Poręcz", "toilets": "Toaleta w obiekcie", "fee": "Opłata",
    "opening_hours": "Godziny otwarcia", "capacity:disabled": "Miejsca parkingowe dla osób z niepełnosprawnościami",
}
# grupy do wyswietlania na karcie: wejscie / w srodku / orientacja
ATTR_GROUP = {
    "wheelchair": "wejscie", "wheelchair:description": "wejscie", "door:width": "wejscie", "entrance": "wejscie",
    "step_count": "wejscie", "ramp": "wejscie", "ramp:wheelchair": "wejscie", "automatic_door": "wejscie", "handrail": "wejscie",
    "capacity:disabled": "wejscie", "elevator": "w_srodku", "toilets": "w_srodku", "toilets:wheelchair": "w_srodku",
    "changing_table": "w_srodku", "hearing_loop": "w_srodku", "fee": "w_srodku", "opening_hours": "w_srodku",
    "tactile_paving": "orientacja", "lit": "orientacja", "bench": "orientacja",
}
GROUP_LABEL = {"wejscie": "Wejście", "w_srodku": "W środku", "orientacja": "Orientacja i otoczenie", "inne": "Inne"}
# dodatkowe cechy zalezne od rodzaju miejsca (np. toaleta: oplata i godziny)
CATEGORY_EXTRA = {"toilets": ["fee", "opening_hours", "changing_table", "toilets:wheelchair"], "elevator": ["opening_hours"],
                  "building": ["elevator", "ramp:wheelchair", "toilets", "toilets:wheelchair"]}
VALUE_TEXT = {"yes": "tak", "no": "nie", "limited": "ograniczony", "designated": "przystosowany"}
ALLOWED_REPORT_ATTRS = set(ATTR_LABELS)
# rodzaje udogodnien do wyszukiwania "najblizszej ..." (klucz -> wartosci amenity/tourism z OSM)
NEAREST_KINDS = {
    "toaleta": {"label": "Toaleta publiczna", "cat": {"toilets"}}, "lawka": {"label": "Ławka", "cat": {"bench"}},
    "apteka": {"label": "Apteka", "cat": {"pharmacy"}}, "przychodnia": {"label": "Przychodnia / lekarz", "cat": {"clinic", "doctors", "hospital"}},
    "kawiarnia": {"label": "Kawiarnia", "cat": {"cafe"}}, "restauracja": {"label": "Restauracja", "cat": {"restaurant", "fast_food"}},
    "woda": {"label": "Woda pitna", "cat": {"drinking_water"}}, "bankomat": {"label": "Bankomat", "cat": {"atm"}},
    "poczta": {"label": "Poczta", "cat": {"post_office"}}, "muzeum": {"label": "Muzeum", "cat": {"museum", "gallery"}},
    "parking": {"label": "Parking", "cat": {"parking"}}, "winda": {"label": "Winda", "cat": {"elevator"}},
    "budynek": {"label": "Budynek użyteczności publicznej", "cat": {"building"}},
}
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


def parse_width_m(v) -> float | None:
    """door:width z OSM: "0.9", "0,85", "90 cm", "1.2 m" -> metry (liczby >5 traktujemy jako cm)."""
    if v is None:
        return None
    t = str(v).lower().replace(",", ".").strip()
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*(cm|m)?", t)
    if not m:
        return None
    x = float(m.group(1))
    if m.group(2) == "cm" or (m.group(2) is None and x > 5):
        x /= 100
    return x


def osm_links(fid: str, lon: float, lat: float) -> dict:
    """Linki do poprawienia zrodla (OSM): edycja obiektu i notatka. Zamiast utrzymywac wlasna baze, kierujemy poprawke do zrodla."""
    typ, _, oid = (fid or "").partition("/")
    edit = f"https://www.openstreetmap.org/edit?{typ}={oid}" if typ in ("node", "way", "relation") and oid.isdigit() else None
    return {"osm_edit_url": edit, "osm_object_url": f"https://www.openstreetmap.org/{typ}/{oid}" if edit else None,
            "osm_note_url": f"https://www.openstreetmap.org/note/new#map=19/{lat:.6f}/{lon:.6f}"}


def client_ip(request: Request) -> str:
    """Adres klienta do limitu zgloszen (trzymany tylko w pamieci). Za reverse proxy ustaw TRUST_PROXY=1,
    wtedy bierzemy pierwszy adres z X-Forwarded-For (inaczej wszyscy mieliby adres proxy)."""
    if os.getenv("TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "?"


# waga "waznosci" miejsca przy priorytetyzacji brakujacych danych (uslugi publiczne i zdrowie wyzej)
GAP_WEIGHT = {"hospital": 10, "clinic": 9, "doctors": 9, "pharmacy": 8, "townhall": 8, "toilets": 8, "post_office": 7,
              "police": 7, "courthouse": 7, "bank": 6, "library": 6, "museum": 6, "theatre": 6, "cinema": 5, "hotel": 5,
              "university": 5, "school": 5, "restaurant": 4, "cafe": 4, "supermarket": 4}


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


class Moderation(BaseModel):
    action: str = Field(..., pattern="^(zaakceptowane|odrzucone)$")
    note: str | None = Field(None, max_length=300)


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
            if cat is None:   # winda, stacja, budynek (np. szpital, urzad) - tez sa miejscami z cechami dostepnosci
                cat = ("elevator" if p.get("highway") == "elevator" else "station" if (p.get("railway") or p.get("public_transport"))
                       else "building" if p.get("building") else None)
            self.places[fid] = {"id": fid, "name": p.get("name"), "category": cat,
                                "lon": geom["coordinates"][0], "lat": geom["coordinates"][1], "norm": norm(p.get("name") or "")}
        self.facts: dict = {}
        for r in facts:
            self.facts.setdefault(r["feature_id"], {}).setdefault(r["attribute"], []).append(r)
        self.reports: list = json.loads(reports_path.read_text("utf-8")) if reports_path.exists() else []
        self.outage = False
        self.confirmed: dict = {}      # report_id -> zbior IP (tylko w pamieci, nie zapisujemy)
        self._barriers: dict = {}
        self.hits: dict = {}

    # ---- zgloszenia ----
    def save_reports(self):
        self.reports_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_path.write_text(json.dumps(self.reports, ensure_ascii=False, indent=1), "utf-8")

    def rate_ok(self, ip: str, limit: int = 10, window: int = 3600) -> bool:
        now = time.time()
        if len(self.hits) > 20000:      # ochrona pamieci przed zalewem roznych adresow
            self.hits.clear()
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
        base = {"attribute": attr, "label": ATTR_LABELS.get(attr, attr), "group": ATTR_GROUP.get(attr, "inne")}
        versions = []
        for f in self.facts.get(fid, {}).get(attr, []):
            versions.append({"value": f["value"], "source": f["source"], "source_url": f.get("source_url"),
                             "license": f.get("license"), "observed_at": f.get("observed_at"),
                             "retrieved_at": f.get("retrieved_at"), "confidence": f.get("confidence"), "status": f["status"],
                             "observed_basis": f.get("observed_basis"), "last_edit_at": f.get("last_edit_at")})
        p_ = self.places.get(fid) or {}
        for r in self.reports:
            if r["feature_id"] == fid and r["attribute"] == attr and r.get("moderation") != "odrzucone":
                n = int(r.get("confirmations", 0))
                ok = r.get("moderation") == "zaakceptowane"
                src = ("zgłoszenie użytkownika, zweryfikowane przez moderatora" if ok else "zgłoszenie użytkownika") + \
                      (" (PRZYKŁADOWE - dane demo)" if r.get("demo") else "")
                versions.append({"value": r["value"], "source": src, "source_url": None, "license": None,
                                 "observed_at": r["created_at"][:10], "retrieved_at": r["created_at"][:10],
                                 "confidence": 0.7 if ok else min(0.3 + 0.05 * n, 0.5),
                                 "status": "potwierdzone" if ok else "niezweryfikowane", "comment": r.get("comment"),
                                 "report_id": r["id"], "confirmations": n,
                                 "community_text": (f"{n} os. potwierdziło to zgłoszenie" if n else "nikt jeszcze nie potwierdził"),
                                 "user_report": True,
                                 **(osm_links(fid, p_["lon"], p_["lat"]) if p_ else {})})
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

    FIT_TEXT = {"tak": "spełnia", "nie": "nie spełnia", "czesciowo": "spełnia częściowo", "brak_danych": "brak danych",
                "sprzeczne": "sprzeczne dane"}

    def fit(self, fid: str, prof: dict) -> dict:
        """Dopasowanie miejsca do preferencji: lista warunkow z werdyktem i zrodlem. Nigdy nie zgadujemy:
        brak danych = „brak danych”; „pasuje” tylko, gdy WSZYSTKIE sprawdzone warunki sa spelnione i potwierdzone."""
        hard, w, needs = prof.get("hard", {}), prof.get("weights", {}), prof.get("needs", [])
        wanted = []     # (atrybut, etykieta, typ)
        if hard.get("forbid_steps") or hard.get("require_kerb") or "tramwaje_niskopodlogowe" in needs or "windy" in needs:
            wanted.append(("wheelchair", "Wejście bez schodów / dostęp dla wózka", "bool"))
        if hard.get("min_width_m"):
            wanted.append(("door:width", f"Szerokość wejścia co najmniej {hard['min_width_m']:g} m", "width"))
        if any(n in needs for n in ("toalety_dostepne", "toalety")):
            wanted.append(("toilets:wheelchair", "Toaleta dostępna dla wózka", "bool"))
        if "przewijak" in needs:
            wanted.append(("changing_table", "Przewijak", "bool"))
        if "petla_indukcyjna" in needs:
            wanted.append(("hearing_loop", "Pętla indukcyjna", "bool"))
        if "no_tactile_paving" in w or "prowadzenie_dotykowe" in needs:
            wanted.append(("tactile_paving", "Prowadzenie dotykowe", "bool"))
        if "unlit" in w or "oswietlenie" in needs:
            wanted.append(("lit", "Oświetlenie", "bool"))
        if "lawki" in needs or "long_segment_no_rest" in w:
            wanted.append(("bench", "Miejsce do odpoczynku", "bool"))
        checks = []
        for attr, label, typ in wanted:
            row = self.attr_row(fid, attr)
            v, st = row.get("value"), row["status"]
            if st == "brak":
                verdict = "brak_danych"
            elif st == "sprzeczne":
                verdict = "sprzeczne"
            elif typ == "width":
                wm = parse_width_m(v)
                verdict = "brak_danych" if wm is None else ("tak" if wm >= hard["min_width_m"] else "nie")
            elif v in ("yes", "designated"):
                verdict = "tak"
            elif v == "limited":
                verdict = "czesciowo"
            elif v == "no":
                verdict = "nie"
            else:
                verdict = "brak_danych"
            checks.append({"attribute": attr, "label": label, "verdict": verdict, "verdict_text": self.FIT_TEXT[verdict],
                           "value_text": row.get("value_text"), "status": st, "source": row.get("source"),
                           "observed_at": row.get("observed_at")})
        if not checks:
            return {"verdict": "brak_kryteriow", "text": "Wybrane preferencje nie dotyczą cech obiektu.", "checks": []}
        vs = {c["verdict"] for c in checks}
        confirmed = all(c["status"] == "potwierdzone" for c in checks)
        if "nie" in vs:
            verdict, text = "nie_pasuje", "Nie spełnia części Twoich wymagań."
        elif "sprzeczne" in vs:
            verdict, text = "sprzeczne", "Dane są sprzeczne - sprawdź przed wizytą."
        elif "brak_danych" in vs or "czesciowo" in vs:
            verdict, text = "brak_danych", "Brak pełnych danych - nie wiadomo, czy spełnia wszystkie wymagania."
        elif confirmed:
            verdict, text = "pasuje", "Spełnia wymagania według potwierdzonych danych (bez gwarancji)."
        else:
            verdict, text = "prawdopodobnie_pasuje", "Prawdopodobnie spełnia wymagania, ale dane nie są potwierdzone."
        return {"verdict": verdict, "text": text, "checks": checks}

    def card(self, fid: str, profile: str | None, prof: dict | None = None, place: dict | None = None) -> dict:
        p = place or self.places.get(fid)
        if not p:
            raise HTTPException(404, detail="Nie znaleziono miejsca")
        base_attrs = list(PROFILE_ATTRS.get(profile, DEFAULT_ATTRS) if profile else DEFAULT_ATTRS)
        attrs = base_attrs + [a for a in CATEGORY_EXTRA.get(p["category"], []) if a not in base_attrs]
        rows = [self.attr_row(fid, a) for a in attrs]
        missing = [r["label"] for r in rows if r["status"] == "brak"]
        more = len(missing) - 4
        if more > 0:
            missing = missing[:4]
        wc = next((r for r in rows if r["attribute"] == "wheelchair"), None)
        if all(r["status"] == "brak" for r in rows):
            summary = {"level": "brak", "text": "Brak danych o dostępności. Nie zakładamy, że miejsce jest dostępne."}
        elif any(r["status"] == "sprzeczne" for r in rows):
            summary = {"level": "sprzeczne", "text": "Źródła podają sprzeczne informacje. Sprawdź przed wizytą."}
        elif wc and wc["value"] in ("yes", "designated"):
            extra = f" Brak szczegółów: {', '.join(missing)}{f' oraz {more} innych' if more > 0 else ''}." if missing else ""
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
                "summary": summary, "attributes": rows, "banner": banner, "grupy": GROUP_LABEL,
                "w_poblizu": self.nearby_features(fid, p),
                "fit": self.fit(fid, prof) if prof else None}

    NEARBY = (("elevator", "winda", 60), ("toilets", "toaleta", 200))

    def nearby_features(self, fid: str, me: dict | None = None) -> list:
        """Windy i toalety publiczne blisko miejsca (odleglosc w LINII PROSTEJ - to nie jest trasa). Pomaga, gdy sam obiekt nie ma tych danych."""
        me = me or self.places[fid]
        out = []
        for cat, kind, radius in self.NEARBY:
            if me["category"] == cat:
                continue
            found = []
            for pid, q in self.places.items():
                if q["category"] != cat or pid == fid:
                    continue
                d = dist_m((me["lon"], me["lat"]), (q["lon"], q["lat"]))
                if d <= radius:
                    found.append((d, pid, q))
            for d, pid, q in sorted(found)[:2]:
                wc = self.attr_row(pid, "wheelchair")
                out.append({"kind": kind, "id": pid, "name": q["name"] or ("Winda" if kind == "winda" else "Toaleta publiczna"),
                            "distance_m": round(d), "line_of_sight": True, "lon": q["lon"], "lat": q["lat"],
                            "wheelchair": {"value_text": wc.get("value_text"), "status": wc["status"], "source": wc.get("source"),
                                           "observed_at": wc.get("observed_at")}})
        return out


def parse_profiles(s: str, prefs: str | None = None) -> list:
    """profiles = gotowe zestawy (klucze); prefs = wlasne preferencje (np. "nostairs,incline:6,kerb"), bez nazw grup."""
    keys = [k.strip() for k in (s or "").split(",") if k.strip()]
    bad = [k for k in keys if k not in PROFILES]
    if bad:
        raise HTTPException(422, detail=f"Nieznany profil: {bad}. Dostępne: {list(PROFILES)}")
    if prefs and prefs.strip():
        try:
            keys = build_profile(keys, prefs)
        except ValueError as e:
            raise HTTPException(422, detail={"message": str(e), "dostepne_preferencje": PREF_HELP})
    return keys


# atrybuty, dla ktorych „tak” oznacza UDOGODNIENIE, a „nie/ograniczony” BARIERE (reszta to zwykla informacja)
POSITIVE_ATTRS = {"wheelchair", "toilets:wheelchair", "toilets", "elevator", "ramp:wheelchair", "ramp", "changing_table", "bench",
                  "tactile_paving", "hearing_loop", "lit", "traffic_signals:sound", "traffic_signals:vibration", "automatic_door",
                  "handrail"}


def classify_attributes(rows: list) -> dict:
    """Wiersze karty -> udogodnienia / bariery / informacje / sprzeczne / brak danych. Brak danych NIGDY nie trafia do udogodnien."""
    out = {"udogodnienia": [], "bariery": [], "informacje": [], "sprzeczne": [], "brak_danych": []}

    def item(r):
        return {"attribute": r["attribute"], "label": r["label"], "value": r.get("value"), "value_text": r.get("value_text"),
                "status": r["status"], "source": r.get("source"), "observed_at": r.get("observed_at")}
    for r in rows:
        st, v = r["status"], r.get("value")
        if st == "brak":
            out["brak_danych"].append({"attribute": r["attribute"], "label": r["label"]})
        elif st == "sprzeczne":
            out["sprzeczne"].append({**item(r), "versions": r.get("versions", [])})
        elif r["attribute"] == "step_count":
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                word = "stopień" if n == 1 else "stopnie" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "stopni"
                out["bariery"].append({**item(r), "value_text": f"{n} {word}"})
            else:
                out["informacje"].append(item(r))
        elif r["attribute"] in POSITIVE_ATTRS:
            if v in ("yes", "designated"):
                out["udogodnienia"].append(item(r))
            elif v in ("no", "limited"):
                out["bariery"].append(item(r))
            else:
                out["informacje"].append(item(r))
        else:
            out["informacje"].append(item(r))
    return out


STATUS_SYMBOL = {"potwierdzone": "✓ potwierdzone", "prawdopodobne": "~ prawdopodobne", "niezweryfikowane": "? niezweryfikowane",
                 "sprzeczne": "⚠ sprzeczne", "brak": "– brak danych"}
FIT_SYMBOL = {"tak": "✓", "nie": "✗", "czesciowo": "~", "brak_danych": "?", "sprzeczne": "⚠"}
LEVEL_TEXT = {"pasuje": "✓ Pasuje", "prawdopodobnie_pasuje": "~ Prawdopodobnie pasuje", "nie_pasuje": "✗ Nie pasuje",
              "brak_danych": "? Brak pełnych danych", "sprzeczne": "⚠ Sprzeczne dane", "brak_kryteriow": "Brak kryteriów"}


def render_card_html(card: dict) -> str:
    """Strona obiektu bez JavaScriptu (semantyczny HTML, kontrast AA, tekst zamiast samej ikony) - do osadzenia w iframe
    przez hotele i organizatorow oraz jako tekstowa alternatywa dla mapy."""
    e = lambda x: html.escape("" if x is None else str(x))
    pl = card["place"]
    rows = []
    for a in card["attributes"]:
        src = a.get("source") or "-"
        when = a.get("observed_at") or a.get("retrieved_at") or "-"
        vers = ""
        if len(a.get("versions", [])) > 1:
            vers = "<ul>" + "".join(f"<li>{e(v['value'])} - {e(v['source'])}, {e(v.get('observed_at') or '-')}"
                                   f" ({e(STATUS_SYMBOL.get(v['status'], v['status']))})</li>" for v in a["versions"]) + "</ul>"
        note = f"<br><small>{e(a['note'])}</small>" if a.get("note") else ""
        rows.append(f"<tr><th scope=\"row\">{e(a['label'])}</th><td>{e(a['value_text'])}{vers}{note}</td>"
                    f"<td>{e(STATUS_SYMBOL.get(a['status'], a['status']))}</td><td>{e(src)}</td><td>{e(when)}</td></tr>")
    fit = ""
    if card.get("fit") and card["fit"]["checks"]:
        f = card["fit"]
        items = "".join(f"<li><strong>{e(FIT_SYMBOL[c['verdict']])} {e(c['label'])}</strong>: {e(c['verdict_text'])}"
                        f" ({e(c['value_text'])}, {e(STATUS_SYMBOL.get(c['status'], c['status']))})</li>" for c in f["checks"])
        fit = (f"<section aria-labelledby=\"fit\"><h2 id=\"fit\">Dopasowanie do Twoich wymagań</h2>"
               f"<p><strong>{e(LEVEL_TEXT.get(f['verdict'], f['verdict']))}.</strong> {e(f['text'])}</p><ul>{items}</ul></section>")
    near = ""
    if card.get("w_poblizu"):
        li = "".join(f"<li>{e(x['kind'].capitalize())}: {e(x['name'])}, ok. {e(x['distance_m'])} m w linii prostej "
                     f"({e(x['wheelchair']['value_text'] or 'brak danych')}, {e(STATUS_SYMBOL.get(x['wheelchair']['status'], x['wheelchair']['status']))})</li>"
                     for x in card["w_poblizu"])
        near = f"<section aria-labelledby=\"near\"><h2 id=\"near\">W pobliżu</h2><ul>{li}</ul></section>"
    banner = f"<p role=\"alert\" class=\"warn\">{e(card['banner'])}</p>" if card.get("banner") else ""
    links = osm_links(pl["id"], pl["lon"], pl["lat"])
    fix = (f"<p>Widzisz błąd? <a href=\"{e(links['osm_edit_url'])}\" rel=\"noopener\">Popraw w OpenStreetMap</a> albo "
           f"<a href=\"{e(links['osm_note_url'])}\" rel=\"noopener\">zostaw notatkę</a>.</p>") if links["osm_edit_url"] else ""
    s_ = card["summary"]
    nalot_html = f"<p class=\"mut\">{e(card['nalot']['text'])}</p>" if card.get("nalot") else ""
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(pl['name'] or 'Miejsce')} - dostępność</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#4a4a4a;--line:#c9c9c9;--warn:#7a3b00;--link:#0b4f9c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14161a;--fg:#f1f1f1;--mut:#c4c4c4;--line:#444;--warn:#ffcf99;--link:#9cc7ff}}}}
body{{margin:0;padding:16px;font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:52rem;margin:auto}}h1{{font-size:1.5rem;margin:.2em 0}}h2{{font-size:1.15rem;margin-top:1.4em}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid var(--line);padding:.5em;text-align:left;vertical-align:top}}
caption{{text-align:left;font-weight:600;padding:.4em 0}}small,.mut{{color:var(--mut)}}.warn{{color:var(--warn);font-weight:600}}
a{{color:var(--link)}}a:focus-visible{{outline:3px solid currentColor;outline-offset:2px}}
@media (max-width:640px){{th,td{{display:block;border:0;border-bottom:1px solid var(--line)}}}}
</style></head><body><main>
<h1>{e(pl['name'] or 'Miejsce bez nazwy')}</h1><p class="mut">{e(pl['category'] or '')}</p>{banner}
<section aria-labelledby="sum"><h2 id="sum">Podsumowanie</h2><p role="status"><strong>{e(s_['text'])}</strong></p></section>{fit}
<section aria-labelledby="det"><h2 id="det">Szczegóły i źródła</h2>
<table><caption>Cechy dostępności: wartość, wiarygodność, źródło i data</caption>
<thead><tr><th scope="col">Cecha</th><th scope="col">Wartość</th><th scope="col">Wiarygodność</th><th scope="col">Źródło</th><th scope="col">Data</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>{near}
{nalot_html}<p class="mut">Brak informacji nie oznacza, że miejsce jest dostępne. Zgłoszenia użytkowników są niezweryfikowane, dopóki nie zostaną potwierdzone.</p>{fix}
<footer class="mut"><small>Dane: © OpenStreetMap contributors (ODbL). Kraków bez barier - prototyp.</small></footer>
</main></body></html>"""


def create_app(net: Net | None = None, pois_geojson: dict | None = None, facts: list | None = None,
               cfg: dict | None = None, reports_path: Path | None = None, transit: Transit | None = None,
               realtime: Realtime | None = None, geocoder: Geocoder | None = None, surveys: Surveys | None = None,
               buildings: Buildings | None = None) -> FastAPI:
    cfg = cfg or load_config()
    out = out_dir(cfg)
    if transit is None:
        from pipeline.common import raw_dir
        transit = Transit.from_file(raw_dir(cfg) / "transit.json")
    if surveys is None:
        from pipeline.common import raw_dir as _rd
        surveys = Surveys.from_files(cfg, ROOT, _rd(cfg), load_aoi(cfg))
    if buildings is None:
        bf = out / "buildings.geojson"
        buildings = Buildings(json.loads(bf.read_text("utf-8")) if bf.exists() else None)
    realtime = realtime or Realtime(base=(cfg.get("transit") or {}).get("realtime_base"))
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
    store = Store(net, pois_geojson, facts, cfg, reports_path or Path(os.getenv("REPORTS_PATH") or (ROOT / "data" / "reports.json")))
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

    stop_names: dict = {}
    for _st in transit.stops.values():
        stop_names.setdefault(norm(_st["name"]), []).append(_st)

    def lookup(q: str, limit: int = 8) -> list:
        """Adres / ulica / nazwa miejsca / przystanek -> punkty. Najpierw tak, jak wpisano; gdy nie ma trafienia dokladnego,
        probuje form podstawowych ("Rynku Glownego" -> "Rynek Glowny"), a na koncu poprawia literowki dopasowaniem przyblizonym."""
        res = lookup_once(q, limit, fuzzy=False)
        if res and not all(r.get("fuzzy") or r.get("approximate") for r in res):
            return res
        for cand in deinflect(q):
            alt = lookup_once(cand, limit, fuzzy=False)
            if alt and not all(r.get("fuzzy") or r.get("approximate") for r in alt):
                return alt
        return res or lookup_once(q, limit, fuzzy=True)

    def lookup_once(q: str, limit: int = 8, fuzzy: bool = True) -> list:
        res = geocoder.search(q, limit) if geocoder.available else []
        qn = norm(q)
        alias = (cfg.get("search_aliases") or {}).get(qn)
        if alias:      # potoczna nazwa -> nazwa w OSM, np. "dworzec glowny" -> "Krakow Glowny"
            for p in sorted((p for p in store.places.values() if p["norm"] and alias in p["norm"]), key=lambda p: len(p["norm"]))[:limit]:
                res.insert(0, {"id": p["id"], "label": p["name"], "type": "miejsce", "street": None, "number": None,
                               "lon": p["lon"], "lat": p["lat"], "exact": False, "approximate": False, "fuzzy": False})
            res = res[:limit]
        if len(res) < limit and qn:
            for p in sorted((p for p in store.places.values() if p["norm"] and qn in p["norm"]),
                            key=lambda p: (not p["norm"].startswith(qn), len(p["norm"])))[: limit - len(res)]:
                res.append({"id": p["id"], "label": p["name"], "type": "miejsce", "street": None, "number": None,
                            "lon": p["lon"], "lat": p["lat"], "exact": False, "approximate": False, "fuzzy": False})
        if len(res) < limit and qn:
            hits = sorted((n for n in stop_names if qn in n), key=lambda n: (not n.startswith(qn), len(n)))
            for n in hits[: limit - len(res)]:
                sts = stop_names[n]
                res.append({"id": sts[0]["id"], "label": f"Przystanek {sts[0]['name']}", "type": "przystanek", "street": None,
                            "number": None, "lon": sum(x["lon"] for x in sts) / len(sts), "lat": sum(x["lat"] for x in sts) / len(sts),
                            "exact": False, "approximate": False, "fuzzy": False})
        if fuzzy and not res and len(qn) >= 4:   # literowka: "dworxec glowny" -> "dworzec glowny"
            import difflib
            names = {p["norm"]: ("miejsce", p["name"], p["lon"], p["lat"], p["id"]) for p in store.places.values() if p["norm"]}
            for n, sts in stop_names.items():
                names.setdefault(n, ("przystanek", f"Przystanek {sts[0]['name']}", sts[0]["lon"], sts[0]["lat"], sts[0]["id"]))
            scored = sorted(((max(difflib.SequenceMatcher(None, qn, n).ratio(),
                                  difflib.SequenceMatcher(None, qn, n[: len(qn) + 2]).ratio()), n) for n in names), reverse=True)
            for sc, n in scored[:limit]:
                if sc < 0.82:
                    break
                t, label, lo, la, i = names[n]
                res.append({"id": i, "label": label, "type": t, "street": None, "number": None, "lon": lo, "lat": la,
                            "exact": False, "approximate": False, "fuzzy": True})
        return res

    def resolve_q(q, lon, lat, place, name):
        """Punkt z tekstu (q: adres, ulica, miejsce, przystanek), miejsca (place) albo wspolrzednych. Zwraca (punkt, rozpoznana_etykieta)."""
        if q:
            hits = lookup(q, 1)
            if not hits:
                if not geocoder.available:
                    raise HTTPException(503, detail="Geokodowanie niedostępne (uruchom pipeline.fetch_addresses)")
                raise HTTPException(404, detail=f"Nie znaleziono adresu ({name}): {q}. Spróbuj podać ulicę i numer albo nazwę miejsca.")
            return (hits[0]["lon"], hits[0]["lat"]), hits[0]["label"] + (" (dopasowanie przybliżone)" if hits[0].get("fuzzy") else "")
        return resolve(lon, lat, place, name), None

    app = FastAPI(title="Kraków bez barier - API", version="0.1",
                  description="Trasy i karty miejsc dopasowane do potrzeb. Brak danych nie oznacza dostępności.")
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store") if request.url.path.startswith("/api/") else None
        return resp

    @app.get("/api/meta")
    def meta():
        dates = [f["retrieved_at"] for fs in store.facts.values() for l in fs.values() for f in l]
        return {"bbox": b, "profiles": [{"key": k, "label": v["label"], "needs": v["needs"]} for k, v in PROFILES.items()],
                "modes": {"warn": "ostrzegaj o niepewnych danych", "strict": "tylko pewne"},
                "preferencje": PREF_HELP, "rodzaje_udogodnien": {k: v["label"] for k, v in NEAREST_KINDS.items()},
                "dane_pobrane": max(dates) if dates else None, "miejsc": len(store.places),
                "zgloszen": len(store.reports), "transport": transit.available, "lawki_w_danych": store.net.rest_count, "geokodowanie": geocoder.available, "zrodlo_niedostepne": store.outage, "atrybucja": ATTRIBUTION,
                "ostatni_nalot": (surveys.overview()["last"] or {}).get("date"),
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
        """Adres/ulica/miejsce/przystanek -> wspolrzedne (do pol 'skad/dokad' zamiast klikania w mape). Dziala na danych lokalnych."""
        if not geocoder.available and not store.places:
            raise HTTPException(503, detail="Geokodowanie niedostępne (uruchom pipeline.fetch_addresses)")
        res = lookup(q, limit)
        return {"results": res, "source": geocoder.meta.get("source"), "license": geocoder.meta.get("license"),
                "note": "Tylko adresy zapisane w OpenStreetMap w obszarze demo. Brak wyniku nie oznacza, że adres nie istnieje."}

    @app.get("/api/places")
    def places(q: str = Query(..., min_length=2, max_length=60), limit: int = Query(10, ge=1, le=30)):
        qn = norm(q)
        hits = [p for p in store.places.values() if p["norm"] and qn in p["norm"]]
        hits.sort(key=lambda p: (not p["norm"].startswith(qn), len(p["norm"])))
        return [{k: p[k] for k in ("id", "name", "category", "lon", "lat")} for p in hits[:limit]]

    @app.get("/api/places/{feature_id:path}")
    def place_card(feature_id: str, profile: str | None = None, prefs: str = ""):
        """Karta miejsca. profile = gotowy zestaw; prefs = wlasne preferencje (np. "nostairs,width:0.9"). `fit` = dopasowanie warunek po warunku."""
        if profile and profile not in PROFILES:
            raise HTTPException(422, detail=f"Nieznany profil: {profile}")
        keys = parse_profiles(profile or "", prefs)
        prof = merge_profiles(keys) if keys else None
        card = store.card(feature_id, profile, prof)
        card["nalot"] = surveys.status_at(card["place"]["lon"], card["place"]["lat"])
        if transit.available:
            pl = card["place"]
            acc = profile in ("wozek_inwalidzki", "wozek_dziecko")
            card["transit"] = add_live(transit.nearby_with_departures(
                pl["lon"], pl["lat"], datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None),
                only_accessible=acc), acc)
        return card

    @app.get("/embed/place/{feature_id:path}", response_class=HTMLResponse)
    def embed_place(feature_id: str, profile: str | None = None, prefs: str = ""):
        """Dostepna strona obiektu (HTML bez JS) do wstawienia w <iframe> na stronie hotelu/wydarzenia."""
        card = place_card(feature_id, profile, prefs)
        return HTMLResponse(render_card_html(card), headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors *",
            "Cache-Control": "public, max-age=300"})

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

    def route_warnings(r, a, z, a_label, z_label, from_q, to_q) -> list:
        warnings = []
        for q_, lab in ((from_q, a_label), (to_q, z_label)):
            if q_ and lab:
                warnings.append(f"Adres „{q_}” rozpoznano jako: {lab}.")
        if dist_m(a, r["coords"][0]) > 150 or dist_m(z, r["coords"][-1]) > 150:
            warnings.append("Punkt startu lub celu jest daleko od sieci pieszej - trasa zaczyna się w najbliższym dostępnym miejscu.")
        if r["pct_niepewne"] > 0:
            warnings.append(f"{r['pct_niepewne']}% trasy ma niepełne dane - patrz kroki oznaczone UWAGA.")
        if r.get("hazard_counts", {}).get("blokada"):
            warnings.append("Ta trasa przechodzi przez przeszkody, których wybrany profil nie powinien pokonywać - patrz zagrożenia.")
        if store.outage:
            warnings.append("Źródło OpenStreetMap chwilowo niedostępne - dane z zapisu, mogą być nieaktualne.")
        return warnings

    ROUTE_PROPS = ("profile", "mode", "length_m", "time_min", "pct_niepewne", "pct_przeszkody", "steps", "max_do_lawki_m",
                   "lawki_w_danych", "hazards", "hazard_counts", "narration")

    def with_survey(props: dict, coords: list) -> dict:
        """Dokleja informacje o nalotach: swiezosc danych na trasie + obserwacje z nalotow w poblizu trasy jako ostrzezenia.
        Obserwacje nie zmieniaja wyboru trasy (sa tylko informacja z terenu), wiec liczymy je osobno od zagrozen z OSM."""
        props["nalot"] = surveys.route_status(coords)
        obs = surveys.observations_along(coords)
        props["hazards"], props["narration"] = list(props["hazards"]), list(props["narration"])
        props["hazard_counts"] = dict(props["hazard_counts"])
        nid = max([h["id"] for h in props["hazards"]], default=0)
        for o in obs:
            nid += 1
            label, spoken = OBS_TYPES[o["type"]]
            when = o.get("observed_at")
            demo = " (PRZYKŁADOWE - dane demo)" if o.get("demo") else ""
            stamp = datetime.fromisoformat(when).strftime("%d.%m.%Y") if when else "data nieznana"
            txt = f"{label}, zgłoszono podczas nalotu {stamp}{demo}" + (f": {o['text']}" if o.get("text") else "")
            props["hazards"].append({"type": "obserwacja_nalotu", "subtype": o["type"], "severity": "ostrzezenie", "text": txt,
                                     "lon": o["lon"], "lat": o["lat"], "at_m": o["at_m"], "length_m": 0, "street": None, "kind": "obserwacja",
                                     "id": nid, "spoken": f"{label}, według nalotu z {stamp}", "source": f"nalot {stamp}{demo}",
                                     "observed_at": when})
            props["narration"].append({"at_m": o["at_m"], "announce_at_m": max(0, o["at_m"] - 30), "lon": o["lon"], "lat": o["lat"],
                                       "text": f"{spoken.capitalize()} (według nalotu z {stamp})", "severity": "ostrzezenie",
                                       "hazard_id": nid, "hazard_ids": [nid]})
        if obs:
            props["hazards"].sort(key=lambda h: h["at_m"])
            props["narration"].sort(key=lambda n: n["at_m"])
            props["hazard_counts"]["ostrzezenie"] = props["hazard_counts"].get("ostrzezenie", 0) + len(obs)
        return props

    def route_feature(r, a_label, z_label, warnings, extra=None, max_steps=7) -> dict:
        props = {k: r[k] for k in ROUTE_PROPS}
        props.update(extra or {})
        props = with_survey(props, r["coords"])
        # tryb prosty i tekst do czytania na glos (dla seniorow, ADHD, niewidomych)
        props["simple"] = simple_route(props["steps"], r["coords"], props["length_m"], props["time_min"], props["hazard_counts"], max_steps)
        props["spoken_summary"] = spoken_summary(props)
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": r["coords"]},
                "properties": {**props, "start_label": a_label, "end_label": z_label, "warnings": warnings,
                               "atrybucja": ATTRIBUTION}}

    @app.get("/api/route")
    def route(from_lon: float | None = None, from_lat: float | None = None, from_place: str | None = None,
              to_lon: float | None = None, to_lat: float | None = None, to_place: str | None = None,
              from_q: str | None = Query(None, max_length=100), to_q: str | None = Query(None, max_length=100),
              profiles: str = "", prefs: str = "", mode: str = Query("warn", pattern="^(warn|strict)$")):
        keys = parse_profiles(profiles, prefs)
        (a, a_label), (z, z_label) = (resolve_q(from_q, from_lon, from_lat, from_place, "from"),
                                      resolve_q(to_q, to_lon, to_lat, to_place, "to"))
        r = store.net.route(a, z, keys, mode)
        if r is None:
            raise HTTPException(404, detail={"message": "Nie znaleziono trasy dla tego profilu.",
                                             "hint": "W trybie 'strict' trasa może nie istnieć przy brakach danych. Spróbuj mode=warn."})
        return route_feature(r, a_label, z_label, route_warnings(r, a, z, a_label, z_label, from_q, to_q))

    @app.get("/api/routes")
    def routes(from_lon: float | None = None, from_lat: float | None = None, from_place: str | None = None,
               to_lon: float | None = None, to_lat: float | None = None, to_place: str | None = None,
               from_q: str | None = Query(None, max_length=100), to_q: str | None = Query(None, max_length=100),
               profiles: str = "", prefs: str = "", simple_steps: int = Query(7, ge=3, le=9)):
        """Kilka wariantow trasy do wyboru (najbardziej dostepna / zrownowazona / najkrotsza) z listami zagrozen.
        Zagrozenia maja wspolrzedne (lon, lat) i odleglosc od startu (at_m) - do znacznikow na mapie i komunikatow glosowych."""
        keys = parse_profiles(profiles, prefs)
        (a, a_label), (z, z_label) = (resolve_q(from_q, from_lon, from_lat, from_place, "from"),
                                      resolve_q(to_q, to_lon, to_lat, to_place, "to"))
        alts = store.net.route_alternatives(a, z, keys)
        if not alts:
            raise HTTPException(404, detail={"message": "Nie znaleziono trasy dla tego profilu.",
                                             "hint": "Punkty mogą leżeć w odciętych częściach sieci. Spróbuj innego początku lub celu."})
        feats = []
        for r in alts:
            extra = {k: r[k] for k in ("id", "label", "recommended", "extra_m", "extra_pct", "tez_jako")}
            feats.append(route_feature(r, a_label, z_label, route_warnings(r, a, z, a_label, z_label, from_q, to_q), extra, simple_steps))
        return {"routes": feats, "recommended": next(r["id"] for r in alts if r["recommended"]),
                "legenda_zagrozen": {"blokada": "przeszkoda nie do pokonania dla wybranego profilu",
                                     "ostrzezenie": "utrudnienie", "brak_danych": "brak danych - nie wiadomo, czy jest przejezdnie"},
                "uwaga": "Zagrożenia pochodzą z danych OSM i NMT; brak zagrożenia na liście nie gwarantuje, że go nie ma."}

    @app.get("/api/plan")
    def plan(from_lon: float | None = None, from_lat: float | None = None, from_place: str | None = None,
             to_lon: float | None = None, to_lat: float | None = None, to_place: str | None = None,
             from_q: str | None = Query(None, max_length=100), to_q: str | None = Query(None, max_length=100),
             profiles: str = "", prefs: str = "", accessible_only: bool | None = None):
        """Plan podrozy: spacer (z przeszkodami wg profilu) + tramwaj/autobus jednym kursem + spacer. Czas: teraz (Europe/Warsaw).
        accessible_only: domyslnie wlaczone dla profili wozkowych (pokazujemy tylko pojazdy `yes`/`likely`)."""
        keys = parse_profiles(profiles, prefs)
        (a, a_label), (z, z_label) = (resolve_q(from_q, from_lon, from_lat, from_place, "from"),
                                      resolve_q(to_q, to_lon, to_lat, to_place, "to"))
        now = datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None, microsecond=0)
        res = plan_multimodal(store.net, transit, realtime, a, z, keys, now, accessible_only)

        def leg_feature(r, label):
            return route_feature(r, a_label if label == "to" else None, z_label if label == "from" else None, [])
        options = []
        for o in res["options"]:
            ride = o["ride"]
            live = None
            full = transit.stops.get(o.pop("_board_id"))
            try:
                if full:
                    lv = realtime.live_for_stop(full, transit.trips, n=10)
                    live = {**{k: lv.get(k) for k in ("available", "stale", "updated_at", "note", "reason", "source")},
                            "departures": [d for d in lv.get("departures", []) if d.get("line") == ride["line"]][:3]}
            except Exception:
                live = {"available": False, "departures": []}
            o["walk_to"], o["walk_from"] = leg_feature(o["walk_to"], "to"), leg_feature(o["walk_from"], "from")
            o["live_at_board_stop"] = live
            options.append(o)
        wo = res["walk_only"]
        walk_only = route_feature(wo, a_label, z_label, route_warnings(wo, a, z, a_label, z_label, from_q, to_q)) if wo else None
        notes = list(res["notes"])
        if wo and options and all(o["total_min"] >= wo["time_min"] for o in options):
            notes.insert(0, "Pieszo jest szybciej niż komunikacją - pokazujemy przejazdy tylko jako opcję.")
        return {"walk_only": walk_only, "options": options, "notes": notes, "accessible_only": res["accessible_only"],
                "excluded_inaccessible": res["excluded_inaccessible"],
                "uwaga": "Dostępność przystanków nie jest w danych ZTP. Pojazd: autobus = deklaracja MPK (prawdopodobnie), tramwaj = dane na żywo + typ taboru."}

    @app.get("/api/kerbs")
    def kerbs():
        """Przejscia i krawezniki z klasa wysokosci (wysoki / obnizony / rowny / pochyly / brak_danych) - warstwa na mape."""
        cf = out / "crossings.geojson"
        if not cf.exists():
            raise HTTPException(503, detail="Brak crossings.geojson (uruchom pipeline.fetch_osm)")
        data = json.loads(cf.read_text("utf-8"))
        feats = []
        for f in data.get("features", []):
            pr = f.get("properties", {})
            if pr.get("kerb") is None and pr.get("highway") not in ("crossing",):
                continue
            ki = kerb_info(as_set(pr.get("kerb")))
            feats.append({"type": "Feature", "geometry": f["geometry"],
                          "properties": {"feature_id": pr.get("feature_id"), "kerb": pr.get("kerb"), "kerb_class": ki["class"],
                                         "kerb_text": ki["text"], "tactile_paving": pr.get("tactile_paving"),
                                         "crossing": pr.get("crossing"), "source": "OpenStreetMap",
                                         "status": "niezweryfikowane" if ki["class"] != "brak_danych" else "brak"}})
        counts = {}
        for f in feats:
            c = f["properties"]["kerb_class"]
            counts[c] = counts.get(c, 0) + 1
        return {"type": "FeatureCollection", "features": feats, "counts": counts,
                "uwaga": "Wysokość krawężnika z OSM (kerb=*): wysoki >3 cm, obniżony do 3 cm, zrównany ok. 0 cm. Brak tagu = brak danych, nie ‚obniżony’."}

    def _ambiguous(qq: str, hits: list):
        """Kilka roznych MIEJSC pasuje do podanej nazwy i zadne nie jest dokladnie ta nazwa -> trzeba dopytac (nie zgadujemy)."""
        qn = norm(qq)
        if qn in (cfg.get("search_aliases") or {}) or len(hits) < 2:
            return None
        places_ = [h for h in hits if h["type"] in ("miejsce", "przystanek") and not h.get("fuzzy")]
        labels = {norm(h["label"]) for h in places_}
        if len(labels) >= 2 and qn not in labels and not any(norm(h["label"]) == qn for h in places_):
            return places_[:3]
        return None

    @app.get("/api/voice/command")
    def voice_command(q: str = Query(..., min_length=1, max_length=200)):
        """Polecenie glosowe (tekst z rozpoznawania mowy w przegladarce) -> intencja + gotowe wywolanie API + odpowiedz do przeczytania.
        Kontekst rozmowy (poprzednia trasa, lista wyborow) trzyma front; serwer jest bezstanowy."""
        cmd = parse_command(q)
        out_ = {**cmd, "heard": q}
        profiles_s = ",".join(cmd.get("profiles") or [])
        prefs_s = cmd.get("prefs") or ""
        if cmd["intent"] == "route":
            call = {"endpoint": "/api/routes", "params": {"profiles": profiles_s, **({"prefs": prefs_s} if prefs_s else {})}}
            miss = []
            for key, qq in (("from", cmd.get("from_q")), ("to", cmd.get("to_q"))):
                if not qq:
                    continue
                hits = lookup(qq, 4)
                amb = _ambiguous(qq, hits) if hits else None
                if amb and "clarify" not in out_:
                    out_["clarify"] = {"slot": key, "choices": [{"n": i, "label": h["label"], "lon": h["lon"], "lat": h["lat"], "id": h["id"]}
                                                                  for i, h in enumerate(amb, 1)]}
                    continue
                if hits:
                    h = hits[0]
                    call["params"][f"{key}_lon"], call["params"][f"{key}_lat"] = h["lon"], h["lat"]
                    out_.setdefault("resolved", {})[key] = h["label"]
                else:
                    miss.append(qq)
            if miss:
                out_["intent"] = "not_found"
                out_["reply"] = "Nie znalazłam w obszarze demo: " + ", ".join(miss) + ". Spróbuj podać ulicę i numer."
            elif "clarify" in out_:
                cl = out_["clarify"]
                names = ", ".join(f"{c['n']}. {c['label']}" for c in cl["choices"])
                out_["intent"] = "clarify"
                out_["reply"] = f"Znalazłam kilka miejsc: {names}. Które wybierasz? Powiedz numer."
                out_["call"] = call      # front dopisuje {slot}_lon/{slot}_lat z wybranej opcji
            else:
                if cmd.get("from_gps"):
                    call["needs_gps"] = "from"
                out_["call"] = call
        elif cmd["intent"] == "nearest":
            params = {"kind": cmd["kind"], "profiles": profiles_s, **({"prefs": prefs_s} if prefs_s else {})}
            out_["call"] = {"endpoint": "/api/nearest", "params": params, "needs_gps": "lon,lat"}
            out_["reply"] = f"Szukam najbliższego miejsca: {NEAREST_KINDS[cmd['kind']]['label'].lower()}." + \
                            (" Potem wyznaczę trasę." if cmd.get("route_to_first") else "")
        elif cmd["intent"] == "where_am_i":
            out_["call"] = {"endpoint": "/api/whereami", "params": {}, "needs_gps": "lon,lat"}
        elif cmd["intent"] == "transit_nearby":
            out_["call"] = {"endpoint": "/api/transit/nearby", "params": {}, "needs_gps": "lon,lat"}
        elif cmd["intent"] == "set_profile":
            out_["set"] = {"profiles": profiles_s, "prefs": prefs_s}
        return out_

    def building_address(b: dict, lon: float, lat: float) -> dict | None:
        """Adres budynku: z jego tagow, potem z punktu adresowego w obrysie, na koncu najblizszy adres (oznaczony jako przyblizony)."""
        lab = Buildings.label(b) if b else None
        if lab:
            return {"label": lab, "street": b["street"], "number": b["number"], "distance_m": 0, "approximate": False,
                    "source": "znacznik adresowy budynku w OpenStreetMap"}
        if b and geocoder.available:
            import shapely
            inside_pts = [e for e in geocoder.entries if e["type"] == "adres" and shapely.contains_xy(b["geom"], e["lon"], e["lat"])]
            if inside_pts:
                e = min(inside_pts, key=lambda e: dist_m((e["lon"], e["lat"]), (b["centroid"].x, b["centroid"].y)))
                return {"label": f"{e['street']} {e['number']}", "street": e["street"], "number": e["number"], "distance_m": 0,
                        "approximate": False, "source": "punkt adresowy w obrysie budynku (OpenStreetMap)"}
        a = geocoder.reverse(lon, lat) if geocoder.available else None
        if a:
            return {"label": a["label"].replace(" (ulica)", ""), "street": a["street"], "number": a.get("number"),
                    "distance_m": a["distance_m"], "approximate": True,
                    "source": "najbliższy adres w danych OpenStreetMap" if a["type"] == "adres" else "najbliższa ulica w danych OpenStreetMap"}
        return None

    @app.get("/api/at")
    def at_point(lon: float, lat: float, profiles: str = "", prefs: str = "", snap_m: float = Query(10, ge=0, le=30)):
        """Klik w mape: co jest w tym miejscu. Wspolrzedne -> budynek (obrys z OSM) albo najblizszy obiekt -> adres, udogodnienia,
        bariery i to, czego nie wiemy. Dziala tak samo dla budynku bez danych (wtedy: sam adres i „brak danych”)."""
        keys = parse_profiles(profiles, prefs)
        prof = merge_profiles(keys) if keys else None
        profile = keys[0] if len(keys) == 1 and keys[0] in PROFILES else None
        if not inside(lon, lat):
            msg = "To miejsce jest poza obszarem demo (Kraków-Śródmieście), więc nie mamy tu danych."
            return {"inside_area": False, "found": "nic", "text": msg, "spoken": msg}
        b, bdist = buildings.at(lon, lat, snap_m)
        near = sorted(((dist_m((lon, lat), (p_["lon"], p_["lat"])), p_) for p_ in store.places.values()), key=lambda x: x[0])
        if b and bdist > 0 and near and near[0][0] < bdist:      # klik obok budynku, ale tuz przy innym obiekcie (lawka, przystanek)
            b = None
        place, kind = None, "nic"
        if b:
            kind, fid = "budynek", b["id"]
            place = store.places.get(fid) or {"id": fid, "name": b.get("name"), "category": "building",
                                               "lon": round(b["centroid"].x, 6), "lat": round(b["centroid"].y, 6), "norm": norm(b.get("name") or "")}
        else:
            if near and near[0][0] <= max(snap_m, 25):
                place, kind, fid = near[0][1], "obiekt", near[0][1]["id"]
        address = building_address(b, lon, lat) if b else (geocoder.reverse(lon, lat) if geocoder.available else None)
        if address and not b:
            address = {"label": address["label"].replace(" (ulica)", ""), "street": address["street"], "number": address.get("number"),
                       "distance_m": address["distance_m"], "approximate": True,
                       "source": "najbliższy adres w danych OpenStreetMap" if address["type"] == "adres" else "najbliższa ulica w danych OpenStreetMap"}
        res = {"inside_area": True, "found": kind, "click": {"lon": lon, "lat": lat}, "address": address,
               "building": None, "place": None, "summary": None, "udogodnienia": [], "bariery": [], "informacje": [],
               "sprzeczne": [], "brak_danych": [], "w_budynku": [], "w_poblizu": [], "fit": None, "nalot": surveys.status_at(lon, lat),
               "grupy": GROUP_LABEL, "uwaga": "Brak danych nie oznacza, że udogodnienie jest. Dane z OpenStreetMap są niezweryfikowane, "
                                              "jeśli nie mają statusu „potwierdzone”."}
        if place:
            card = store.card(place["id"], profile, prof, place=place)
            res.update(classify_attributes(card["attributes"]))
            res.update({"place": card["place"], "summary": card["summary"], "attributes": card["attributes"],
                        "w_poblizu": card["w_poblizu"], "fit": card["fit"], "banner": card["banner"],
                        **osm_links(place["id"], place["lon"], place["lat"])})
        if b:
            import shapely
            from shapely.geometry import mapping
            res["building"] = {"id": b["id"], "type": b.get("building"), "name": b.get("name"), "click_distance_m": round(bdist, 1),
                               "footprint": mapping(shapely.set_precision(b["geom"], 1e-6))}
            inside_pl = [p_ for p_ in store.places.values() if p_["id"] != b["id"] and shapely.contains_xy(b["geom"], p_["lon"], p_["lat"])]
            for p_ in sorted(inside_pl, key=lambda x: (x["name"] is None, x["name"] or ""))[:20]:
                wc = store.attr_row(p_["id"], "wheelchair")
                res["w_budynku"].append({"id": p_["id"], "name": p_["name"], "category": p_["category"], "lon": p_["lon"], "lat": p_["lat"],
                                         "wheelchair": {"value_text": wc.get("value_text"), "status": wc["status"], "source": wc.get("source"),
                                                        "observed_at": wc.get("observed_at")}})
        # zdanie do przeczytania na glos: najpierw adres, potem to, co wiemy, potem to, czego nie wiemy
        parts = []
        title = (place or {}).get("name") or (b or {}).get("name")
        if kind == "nic":
            parts.append("W tym miejscu nie ma budynku ani znanego obiektu w naszych danych.")
        else:
            parts.append(("Budynek" if kind == "budynek" else "Obiekt") + (f": {title}." if title else " bez nazwy."))
        if address:
            parts.append(("Adres: " if not address["approximate"] else "Najbliższy adres: ") + address["label"] +
                         (f", około {address['distance_m']} metrów stąd" if address["approximate"] and address["distance_m"] else "") + ".")
        else:
            parts.append("Nie znamy adresu tego miejsca w danych OpenStreetMap.")
        if kind != "nic":
            if res["udogodnienia"]:
                parts.append("Udogodnienia: " + ", ".join(x["label"].lower() for x in res["udogodnienia"][:5]) + ".")
            if res["bariery"]:
                parts.append("Bariery: " + ", ".join(x["label"].lower() + (f" ({x['value_text']})" if x.get("value_text") else "") for x in res["bariery"][:5]) + ".")
            if res["sprzeczne"]:
                parts.append("Sprzeczne informacje: " + ", ".join(x["label"].lower() for x in res["sprzeczne"][:3]) + ".")
            if not res["udogodnienia"] and not res["bariery"]:
                parts.append("Nie mamy danych o udogodnieniach ani barierach.")
            elif res["brak_danych"]:
                parts.append(f"Brak danych o: {', '.join(x['label'].lower() for x in res['brak_danych'][:3])}" +
                             (f" i {len(res['brak_danych']) - 3} innych." if len(res["brak_danych"]) > 3 else "."))
        res["text"] = res["spoken"] = " ".join(parts)
        return res

    @app.get("/api/whereami")
    def whereami(lon: float, lat: float, accuracy_m: float | None = Query(None, ge=0, le=100000)):
        """„Gdzie jestem”: adres/ulica i najblizsze miejsca oraz przystanek, gotowe do przeczytania na glos.
        Wspolrzedne przychodza z urzadzenia (Geolocation API) i nie sa nigdzie zapisywane."""
        if not inside(lon, lat):
            msg = ("Jesteś poza obszarem demo (Kraków-Śródmieście), więc nie mamy tu danych. "
                   "Wybierz punkt na mapie albo wpisz adres w obszarze demo.")
            return {"inside_area": False, "text": msg, "spoken": msg, "address": None, "nearby": [], "stop": None}
        addr = geocoder.reverse(lon, lat) if geocoder.available else None
        near = sorted(((dist_m((lon, lat), (p["lon"], p["lat"])), p) for p in store.places.values() if p["name"]),
                      key=lambda x: x[0])
        nearby = [{"id": p["id"], "name": p["name"], "category": p["category"], "distance_m": round(d)} for d, p in near[:4] if d <= 80]
        stop = min(((dist_m((lon, lat), (st["lon"], st["lat"])), st) for st in transit.stops.values()), key=lambda x: x[0], default=None)
        stop_o = {"id": stop[1]["id"], "name": stop[1]["name"], "mode": stop[1]["mode"], "distance_m": round(stop[0])} \
            if stop and stop[0] <= 200 else None
        parts = []
        if addr:
            parts.append(f"Jesteś przy {'ulicy ' if addr['type'] == 'ulica' else ''}{addr['label'].replace(' (ulica)', '')}.")
        else:
            parts.append("Nie znamy adresu tego miejsca w danych OpenStreetMap.")
        if nearby:
            parts.append("W pobliżu: " + ", ".join(f"{n['name']}, {n['distance_m']} metrów" for n in nearby[:3]) + ".")
        if stop_o:
            parts.append(f"Najbliższy przystanek: {stop_o['name']}, {stop_o['distance_m']} metrów.")
        if accuracy_m and accuracy_m > 50:
            parts.append(f"Uwaga: lokalizacja jest niedokładna, około {round(accuracy_m)} metrów.")
        text = " ".join(parts)
        return {"inside_area": True, "text": text, "spoken": text, "address": addr, "nearby": nearby, "stop": stop_o,
                "accuracy_m": accuracy_m}

    @app.get("/api/nearest")
    def nearest(lon: float, lat: float, kind: str, profiles: str = "", prefs: str = "", accessible: bool = False,
                limit: int = Query(5, ge=1, le=20), max_m: int = Query(1000, ge=100, le=3000)):
        """Najblizsze udogodnienia (toaleta, lawka, apteka...) liczone CHODNIKAMI wg profilu/preferencji, a nie w linii prostej.
        accessible=true: tylko obiekty z tagiem wheelchair=yes/designated (brak tagu = pomijamy, nie zgadujemy)."""
        if kind not in NEAREST_KINDS:
            raise HTTPException(422, detail={"message": "Nieznany rodzaj", "dostepne": {k: v["label"] for k, v in NEAREST_KINDS.items()}})
        if not inside(lon, lat):
            raise HTTPException(422, detail="Punkt poza obszarem demo")
        keys = parse_profiles(profiles, prefs)
        k = NEAREST_KINDS[kind]
        cands = [p for p in store.places.values() if p["category"] in k["cat"]]
        reach = store.net.walk_distances((lon, lat), [(p["lon"], p["lat"]) for p in cands], keys, "warn", cutoff_m=max_m)
        items = []
        for i, d in reach:
            p = cands[i]
            wc = store.attr_row(p["id"], "wheelchair")
            if accessible and wc.get("value") not in ("yes", "designated"):
                continue
            speed = 4.8 if not keys else min(profile_speed(x, 4.8, SPEED_KMH) for x in keys)
            items.append({"id": p["id"], "name": p["name"] or k["label"], "kind": kind, "category": p["category"],
                          "lon": p["lon"], "lat": p["lat"], "walk_m": round(d), "walk_min": round(d / 1000 / speed * 60, 1),
                          "straight_m": round(dist_m((lon, lat), (p["lon"], p["lat"]))),
                          "wheelchair": {"value": wc.get("value"), "value_text": wc.get("value_text"), "status": wc["status"],
                                         "source": wc.get("source"), "observed_at": wc.get("observed_at")}})
        items.sort(key=lambda x: x["walk_m"])
        note = None
        if not items:
            note = (f"Nie znaleziono w promieniu {max_m} m (po chodnikach)" + (" obiektu oznaczonego jako dostępny" if accessible else "") +
                    ". Brak w danych OpenStreetMap nie oznacza, że takiego miejsca nie ma.")
        spoken = note
        if items:
            f0 = items[0]
            wcs = {"potwierdzone": "potwierdzona", "prawdopodobne": "prawdopodobna", "niezweryfikowane": "niezweryfikowana",
                   "sprzeczne": "sprzeczne dane", "brak": "brak danych"}[f0["wheelchair"]["status"]]
            spoken = (f"Najbliżej: {f0['name']}, około {f0['walk_m']} metrów chodnikami, to około {max(1, round(f0['walk_min']))} min. "
                      f"Dostępność: {wcs}." + (f" Kolejne miejsca: {len(items) - 1}." if len(items) > 1 else ""))
        return {"kind": kind, "label": k["label"], "profile": store.net.view(keys).label if keys else "Pieszy (bez ograniczeń)",
                "results": items[:limit], "note": note, "spoken": spoken, "tylko_dostepne": accessible,
                "uwaga": "Odległość liczona po sieci pieszej wg wybranego profilu. Dostępność z OSM jest niezweryfikowana, jeśli nie ma statusu „potwierdzone”."}

    @app.get("/api/isochrone")
    def isochrone(lon: float, lat: float, profiles: str = "", prefs: str = "", minutes: float = Query(15, ge=1, le=30),
                  mode: str = Query("warn", pattern="^(warn|strict)$")):
        keys = parse_profiles(profiles, prefs)
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

    # ---------- statystyki pokrycia i swiezosci danych (wiarygodnosc) ----------
    def compute_stats() -> dict:
        from collections import Counter
        today = datetime.now(timezone.utc).date()

        def months_old(d):
            try:
                y, m, dd = (int(x) for x in str(d)[:10].split("-"))
                return (today.year - y) * 12 + today.month - m
            except (ValueError, TypeError):
                return None
        n = len(store.places)
        named = sum(1 for p in store.places.values() if p["name"])
        cov = {}
        for attr in ATTR_LABELS:
            k = sum(1 for fid in store.places if attr in store.facts.get(fid, {}))
            cov[attr] = {"label": ATTR_LABELS[attr], "miejsc": k, "pct": round(100 * k / n, 1) if n else 0.0}
        status = Counter(f["status"] for fs in store.facts.values() for l in fs.values() for f in l)
        age = Counter()
        for fs in store.facts.values():
            for l in fs.values():
                for f in l:
                    m = months_old(f.get("observed_at") or f.get("last_edit_at"))
                    age["brak daty" if m is None else ("do 12 mies." if m <= 12 else ("12-24 mies." if m <= 24 else "ponad 24 mies."))] += 1
        edges = store.net.edges
        tot_len = sum(e["length"] for e in edges) or 1.0
        inc = Counter()
        for e in edges:
            inc[e["incline_src"] or "brak"] += e["length"]
        crossings = [e for e in edges if e["is_crossing"]]
        kerb_known = sum(1 for e in crossings if e["kerb"] or store.net.ntags[e["u"]]["kerb"] or store.net.ntags[e["v"]]["kerb"])
        rep = store.reports
        return {
            "miejsca": {"razem": n, "z_nazwa": named, "pokrycie_atrybutow": cov, "statusy_faktow": dict(status),
                        "wiek_faktow": dict(age)},
            "siec_piesza": {"dlugosc_km": round(tot_len / 1000, 1), "odcinkow": len(edges),
                            "nachylenie_zrodlo_pct": {k: round(100 * v / tot_len, 1) for k, v in inc.items()},
                            "przejsc": len(crossings), "przejsc_z_danymi_o_krawezniku": kerb_known,
                            "przejsc_z_danymi_o_krawezniku_pct": round(100 * kerb_known / len(crossings), 1) if crossings else 0.0,
                            "lawek_w_danych": store.net.rest_count},
            "komunikacja": {"przystankow": len(transit.stops), "odjazdow_w_rozkladzie": sum(len(v) for v in transit.by_stop.values()),
                            "dostepnosc_w_rozkladzie": transit.has_accessibility_data, "planowanie_przejazdow": transit.can_plan},
            "nalot": {k: v for k, v in surveys.overview().items() if k in ("last", "area_with_fresh_survey_pct", "interval_months", "observations_count")},
            "zgloszenia": {"razem": len(rep), "potwierdzone_przez_innych": sum(1 for r in rep if r.get("confirmations")),
                           "zaakceptowane": sum(1 for r in rep if r.get("moderation") == "zaakceptowane"),
                           "odrzucone": sum(1 for r in rep if r.get("moderation") == "odrzucone"),
                           "przykladowe_demo": sum(1 for r in rep if r.get("demo"))},
            "uwaga": "Brak tagu w OSM = brak danych, nie „niedostępne” i nie „dostępne”. To pokrycie danych, nie ocena miasta."}

    @app.get("/api/stats")
    def stats():
        """Pokrycie i swiezosc danych - uczciwy obraz tego, co wiemy, a czego nie (do ekranu „o danych” i do prezentacji)."""
        return compute_stats()

    @app.get("/api/catalog")
    def profile_catalog_endpoint():
        """Katalog barier i udogodnien do ekranu „Moje wymagania”: sztywne 6 grup z domyslnymi pozycjami + pozycje do wlaczenia/wylaczenia."""
        return profile_catalog()

    @app.get("/api/catalog/resolve")
    def catalog_resolve(profiles: str = "", on: str = "", off: str = ""):
        """Zamienia wybor z ekranu („wlacz te, wylacz tamte” przy wybranych grupach) na gotowy parametr `prefs`,
        zeby front nie musial znac tokenow. on/off: id pozycji z /api/catalog, `on` moze miec parametr (incline:6)."""
        keys = parse_profiles(profiles)
        try:
            prefs = resolve_selection(keys, on.split(","), off.split(","))
        except ValueError as e:
            raise HTTPException(422, detail={"message": str(e), "dostepne": list(CATALOG)})
        final = parse_profiles(profiles, prefs)
        return {"profiles": profiles, "prefs": prefs, "aktywne": sorted(active_items(merge_profiles(final))) if final else [],
                "etykieta": merge_profiles(final)["label"] if final else "Pieszy (bez ograniczeń)"}

    @app.get("/api/profile/schema")
    def profile_schema():
        """Format lokalnego pliku profilu („konto bez konta”): JSON Schema, tryby interfejsu, przyklady i zasady prywatnosci."""
        return localprofile.schema()

    @app.post("/api/profile/validate")
    async def profile_validate(request: Request):
        """Sprawdza plik profilu wczytany przez uzytkownika i zamienia go na parametry API (profiles, prefs).
        NIC nie zapisuje (ani pliku, ani wspolrzednych ulubionych miejsc); odpowiedz zawiera znormalizowany plik do ponownego zapisu u uzytkownika."""
        raw = await request.body()
        if len(raw) > localprofile.MAX_BYTES * 2:
            raise HTTPException(413, detail=f"Plik jest za duży (maks. {localprofile.MAX_BYTES // 1000} kB).")
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, detail="To nie jest poprawny plik JSON.")
        return localprofile.validate(doc, inside=inside)

    @app.get("/api/surveys")
    def surveys_overview():
        """Naloty dronem i kontrole terenowe: kiedy ostatnio, jaka czesc obszaru jest swiezo sprawdzona, co nalot widzi i czego nie widzi."""
        return surveys.overview()

    @app.get("/api/surveys/at")
    def surveys_at(lon: float, lat: float):
        """Kiedy ostatnio sprawdzalismy dane miejsce w terenie i czy dane sa swieze."""
        if not inside(lon, lat):
            raise HTTPException(422, detail="Punkt poza obszarem demo")
        return surveys.status_at(lon, lat)

    @app.get("/api/surveys/observations")
    def surveys_observations(survey_id: str | None = Query(None, max_length=60)):
        """Obserwacje z nalotow jako warstwa mapy (zastawiony chodnik, remont, zniszczona nawierzchnia...)."""
        by_id = {x.get("id"): x for x in surveys.items}
        feats = []
        for o in surveys.observations:
            if survey_id and o.get("survey_id") != survey_id:
                continue
            sv = by_id.get(o.get("survey_id")) or {}
            label, _ = OBS_TYPES[o["type"]]
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [o["lon"], o["lat"]]},
                          "properties": {"type": o["type"], "label": label, "text": o.get("text"), "survey_id": o.get("survey_id"),
                                         "observed_at": sv["_date"].isoformat() if sv.get("_date") else None,
                                         "source": "nalot dronem" if sv.get("type", "dron") == "dron" else "kontrola terenowa",
                                         "demo": bool(sv.get("demo")), "status": "obserwacja terenowa"}})
        return {"type": "FeatureCollection", "features": feats,
                "uwaga": "Obserwacja pokazuje stan z dnia nalotu - mógł się zmienić. Brak obserwacji nie oznacza braku przeszkód."}

    @app.get("/api/gaps")
    def gaps(lon: float | None = None, lat: float | None = None, radius_m: int = Query(1500, ge=100, le=10000),
             category: str | None = Query(None, max_length=40), limit: int = Query(20, ge=1, le=100)):
        """„Pomóż uzupełnić dane”: miejsca, w których brak lub niepewność danych o dostępności kosztuje użytkownika najwięcej.
        Priorytet = waga kategorii (zdrowie i usługi publiczne wyżej) x powód (sprzeczność > brak > stare dane) / odległość.
        Każdy wynik ma linki do poprawy w OSM (poprawka trafia do wszystkich aplikacji) i do zgłoszenia w naszym API."""
        today = datetime.now(timezone.utc).date()
        limit_months = int(cfg.get("freshness_months", 24))
        want = norm(category) if category else None
        origin = (lon, lat) if lon is not None and lat is not None else None
        out_ = []
        for fid, pl_ in store.places.items():
            if not pl_["name"] or (want and norm(pl_["category"] or "") != want):
                continue
            d_ = dist_m(origin, (pl_["lon"], pl_["lat"])) if origin else None
            if d_ is not None and d_ > radius_m:
                continue
            row = store.attr_row(fid, "wheelchair")
            reasons, mult = [], 0.0
            if row["status"] == "sprzeczne":
                reasons.append("źródła podają sprzeczne informacje"); mult = 1.5
            elif row["status"] == "brak":
                reasons.append("brak informacji o dostępności dla wózka"); mult = 1.0
            else:
                ds = row.get("observed_at") or row.get("last_edit_at")
                try:
                    y, m, _ = (int(x) for x in str(ds)[:10].split("-"))
                    age = (today.year - y) * 12 + today.month - m
                except (ValueError, TypeError):
                    age = None
                if row.get("observed_basis") == "last_edit":
                    reasons.append("data to tylko ostatnia edycja obiektu, nikt nie potwierdził wejścia"); mult = 0.6
                elif age is None or age > limit_months:
                    reasons.append(f"dane starsze niż {limit_months} mies. lub bez daty"); mult = 0.7
                elif row["status"] == "niezweryfikowane":
                    reasons.append("tylko zgłoszenie użytkownika, czeka na potwierdzenie"); mult = 0.5
            if not mult:
                continue
            missing = [a for a in ("wheelchair", "entrance", "door:width") if store.attr_row(fid, a)["status"] == "brak"]
            w_ = GAP_WEIGHT.get(pl_["category"] or "", 2)
            score = w_ * mult / (1 + (d_ or 0) / 500)
            out_.append({"id": fid, "name": pl_["name"], "category": pl_["category"], "lon": pl_["lon"], "lat": pl_["lat"],
                         "distance_m": round(d_) if d_ is not None else None, "priorytet": round(score, 2),
                         "powody": reasons, "brakuje": missing, "wheelchair_status": row["status"],
                         "zglos": {"method": "POST", "url": "/api/reports"}, **osm_links(fid, pl_["lon"], pl_["lat"])})
        out_.sort(key=lambda x: -x["priorytet"])
        return {"results": out_[:limit], "razem_kandydatow": len(out_),
                "jak_to_dziala": "Ranking pokazuje, gdzie uzupełnienie danych pomoże najwięcej osób. Poprawka w OpenStreetMap (osm_edit_url) "
                                 "trafia do wszystkich aplikacji; zgłoszenie u nas jest widoczne od razu jako niezweryfikowane."}

    @app.get("/api/export/places")
    def export_places(format: str = Query("csv", pattern="^(csv|geojson)$")):
        """Otwarty eksport dostepnosci miejsc razem z proweniencja (zrodlo, data, pewnosc, status). Licencja jak dane zrodlowe (ODbL);
        zgloszenia uzytkownikow sa w eksporcie oznaczone jako niezweryfikowane."""
        attrs = ["wheelchair", "entrance", "door:width", "toilets:wheelchair"]
        rows = []
        for fid, pl_ in store.places.items():
            rec = {"id": fid, "name": pl_["name"], "category": pl_["category"], "lon": pl_["lon"], "lat": pl_["lat"]}
            for a in attrs:
                r_ = store.attr_row(fid, a)
                key = a.replace(":", "_")
                rec.update({f"{key}_value": r_.get("value"), f"{key}_status": r_["status"], f"{key}_source": r_.get("source"),
                            f"{key}_observed_at": r_.get("observed_at"), f"{key}_confidence": r_.get("confidence")})
            rows.append(rec)
        hdr = {"Content-Disposition": f'attachment; filename="krakow-bez-barier-miejsca.{format}"',
               "X-Attribution": "(c) OpenStreetMap contributors, ODbL 1.0; Krakow bez barier"}
        if format == "geojson":
            feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r_.pop("lon"), r_.pop("lat")]}, "properties": r_}
                     for r_ in rows]
            return Response(json.dumps({"type": "FeatureCollection", "features": feats,
                                        "attribution": "© OpenStreetMap contributors, ODbL 1.0",
                                        "uwaga": "Brak danych nie oznacza dostępności. Zgłoszenia użytkowników są niezweryfikowane."},
                                       ensure_ascii=False), media_type="application/geo+json", headers=hdr)
        import csv
        import io
        buf = io.StringIO()
        w_ = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else ["id"])
        w_.writeheader()
        w_.writerows(rows)
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=hdr)

    @app.get("/api/health")
    def health():
        """Stan systemu i zrodel (do monitoringu i do pokazania, co sie dzieje przy awarii zrodla)."""
        dates = [f["retrieved_at"] for fs in store.facts.values() for l in fs.values() for f in l]
        live = realtime.status() if transit.available else {}
        checks = {"dane_osm": {"ok": bool(store.places) and not store.outage, "pobrane": max(dates) if dates else None,
                               "tryb_awarii": store.outage},
                  "siec_piesza": {"ok": bool(store.net.edges), "odcinkow": len(store.net.edges)},
                  "rozklad_ztp": {"ok": transit.available, "data": transit.meta.get("generated_at")},
                  "dane_na_zywo_ztp": {"ok": bool(live) and all(v["ok"] for v in live.values()), "feedy": live},
                  "geokodowanie": {"ok": geocoder.available}}
        degraded = [k for k, v in checks.items() if not v["ok"]]
        return {"status": "ok" if not degraded else "czesciowo", "niedostepne": degraded, "checks": checks,
                "co_widzi_uzytkownik": {"dane_osm": "komunikat o danych zapisanych i możliwie nieaktualnych",
                                        "dane_na_zywo_ztp": "sam rozkład jazdy z adnotacją „nie czas rzeczywisty”",
                                        "geokodowanie": "wybór punktów kliknięciem na mapie"}}

    @app.get("/api/demo/scenarios")
    def demo_scenarios():
        """Gotowe scenariusze do pokazu: dane sprzeczne, niepelne, brak danych, awaria zrodla, trasa z przeszkodami, tramwaj na zywo.
        Zrodlem sa REALNE miejsca z danych; zgloszenia przykladowe sa oznaczone „dane demo”."""
        def pick(pred):
            for fid, p in store.places.items():
                if p["name"] and pred(fid):
                    return fid
            return None
        rows = lambda fid: [store.attr_row(fid, a) for a in ("wheelchair", "door:width", "entrance", "toilets:wheelchair")]
        sc = []
        f = pick(lambda fid: store.attr_row(fid, "wheelchair")["status"] == "sprzeczne")
        sc.append({"id": "sprzeczne", "title": "Dane sprzeczne (OSM mówi „tak”, zgłoszenie mówi „nie”)", "place_id": f,
                   "url": f"/api/places/{f}" if f else None,
                   "pokaz": "Karta pokazuje obie wersje ze źródłami i datami oraz status „sprzeczne” zamiast zielonego ptaszka.",
                   "brakuje": None if f else "Brak sprzeczności w danych. Uruchom POST /api/dev/seed (dodaje zgłoszenia PRZYKŁADOWE) i odśwież."})
        f = pick(lambda fid: (lambda r: 0 < sum(x["status"] == "brak" for x in r) < len(r) and not any(x["status"] == "sprzeczne" for x in r))(rows(fid)))
        sc.append({"id": "niepelne", "title": "Dane niepełne (część atrybutów jest, części brak)", "place_id": f,
                   "url": f"/api/places/{f}" if f else None,
                   "pokaz": "Karta wypisuje, czego brakuje („Brak szczegółów: …”), i nie nazywa miejsca dostępnym.", "brakuje": None if f else "Nie znaleziono."})
        f = pick(lambda fid: all(x["status"] == "brak" for x in rows(fid)))
        sc.append({"id": "brak_danych", "title": "Brak danych o dostępności", "place_id": f, "url": f"/api/places/{f}" if f else None,
                   "pokaz": "„Brak danych. Nie zakładamy, że miejsce jest dostępne.”", "brakuje": None if f else "Nie znaleziono."})
        sc.append({"id": "awaria_zrodla", "title": "Źródło danych niedostępne (symulacja)", "krok1": "POST /api/dev/outage {\"on\": true}",
                   "krok2": "GET /api/places/{id} - baner z datą zapisanych danych", "krok3": "POST /api/dev/outage {\"on\": false}",
                   "pokaz": "Aplikacja działa na zapisanych danych i mówi, że mogą być nieaktualne; przy awarii ZTP pokazuje sam rozkład."})
        for i, d in enumerate(cfg.get("demo_routes") or [], 1):
            from urllib.parse import quote
            sc.append({"id": f"trasa{i}", "title": d.get("title", "Trasa"), "profile": d.get("profile"),
                       "url": f"/api/routes?from_q={quote(d['from_q'])}&to_q={quote(d['to_q'])}&profiles={d.get('profile', '')}",
                       "plan_url": f"/api/plan?from_q={quote(d['from_q'])}&to_q={quote(d['to_q'])}&profiles={d.get('profile', '')}",
                       "pokaz": "Trzy warianty trasy, znaczniki zagrożeń (kostka, brak danych o krawężniku), komunikaty głosowe."})
        sc.append({"id": "tramwaj_na_zywo", "title": "Dostępność tramwaju: flaga ZTP + typ taboru", "url": "/api/transit/nearby?lon=19.937&lat=50.061",
                   "pokaz": "Przy tramwaju: „flaga ZTP + typ taboru, dwa źródła się zgadzają”; przy autobusie: „prawdopodobnie” z deklaracji MPK."})
        sc.append({"id": "najblizsza_toaleta", "title": "Najbliższa toaleta CHODNIKAMI dla wózka vs dla pieszego",
                   "url": "/api/nearest?lon=19.937&lat=50.061&kind=toaleta&profiles=wozek_inwalidzki",
                   "pokaz": "Odległość po sieci pieszej (nie w linii prostej) zmienia się z profilem."})
        sc.append({"id": "nalot_dronem", "title": "Kiedy ostatnio sprawdzaliśmy teren (nalot dronem) i co nalot widzi",
                   "url": "/api/surveys", "pokaz": "Data ostatniego nalotu, do kiedy dane są świeże, co nalot obejmuje i czego NIE obejmuje. "
                   "Wpis przykładowy jest podpisany „PRZYKŁADOWE - dane demo”."})
        sc.append({"id": "tryb_prosty", "title": "Tryb prosty („dla babci”): trasa w kilku krótkich krokach",
                   "url": "/api/routes?from_q=Floria%C5%84ska%2010&to_q=Dworzec%20G%C5%82%C3%B3wny&profiles=senior&simple_steps=5",
                   "pokaz": "properties.simple: jedno zdanie na krok, kierunek skrętu, ostrzeżenie jako osobne pole; properties.spoken_summary do przeczytania."})
        sc.append({"id": "glos", "title": "Asystent głosowy: „jak dojść do toalety”, „gdzie jestem”",
                   "url": "/api/voice/command?q=jak%20doj%C5%9B%C4%87%20do%20toalety",
                   "pokaz": "Intencja, gotowe wywołanie API i odpowiedź do przeczytania; przy dwuznacznej nazwie asystent dopytuje o numer."})
        return {"scenariusze": sc, "uwaga": "Zgłoszenia oznaczone „PRZYKŁADOWE - dane demo” są sztuczne i mają być tak pokazywane."}

    @app.post("/api/reports", status_code=201)
    def add_report(rep: Report, request: Request):
        ip = client_ip(request)
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
        pl_ = store.places[rep.feature_id]
        return {"id": r["id"], "status": "niezweryfikowane", **osm_links(rep.feature_id, pl_["lon"], pl_["lat"]),
                "message": "Dziękujemy. Zgłoszenie jest widoczne jako niezweryfikowane do czasu potwierdzenia.",
                "wskazowka": "Chcesz poprawić źródło? Użyj linku osm_edit_url - poprawka w OpenStreetMap trafi do wszystkich aplikacji."}

    @app.post("/api/reports/{report_id}/confirm")
    def confirm_report(report_id: str, request: Request):
        """Anonimowe potwierdzenie cudzego zgloszenia ("u mnie tez tak"). Liczy sie raz na urzadzenie (IP w pamieci, nie zapisujemy).
        Zgloszenie nadal jest NIEZWERYFIKOWANE - rosnie tylko licznik i ostroznie pewnosc."""
        ip = client_ip(request)
        if not store.rate_ok(ip, limit=30):
            raise HTTPException(429, detail="Za dużo żądań. Spróbuj później.")
        r = next((x for x in store.reports if x["id"] == report_id and x.get("moderation") != "odrzucone"), None)
        if r is None:
            raise HTTPException(404, detail="Nie znaleziono zgłoszenia")
        seen = store.confirmed.setdefault(report_id, set())
        if ip in seen:
            return {"id": report_id, "confirmations": r.get("confirmations", 0), "message": "Już potwierdzono z tego urządzenia."}
        seen.add(ip)
        r["confirmations"] = int(r.get("confirmations", 0)) + 1
        store.save_reports()
        return {"id": report_id, "confirmations": r["confirmations"], "status": "niezweryfikowane",
                "message": "Dziękujemy. Zgłoszenie nadal jest niezweryfikowane."}

    def admin_ok(token: str | None):
        want = os.getenv("ADMIN_TOKEN")
        if not want:
            raise HTTPException(404, detail="Moderacja wyłączona (brak ADMIN_TOKEN na serwerze)")
        import secrets
        if not token or not secrets.compare_digest(token.encode(), want.encode()):   # porownanie w stalym czasie
            raise HTTPException(401, detail="Zły token")

    @app.get("/api/admin/reports")
    def admin_reports(x_admin_token: str | None = Header(None)):
        """Lista zgloszen do moderacji (naglowek X-Admin-Token = zmienna ADMIN_TOKEN na serwerze)."""
        admin_ok(x_admin_token)
        out_ = []
        for r in store.reports:
            p_ = store.places.get(r["feature_id"]) or {}
            out_.append({**r, "place_name": p_.get("name"), **(osm_links(r["feature_id"], p_["lon"], p_["lat"]) if p_ else {})})
        return sorted(out_, key=lambda r: (r.get("moderation") is not None, -int(r.get("confirmations", 0))))

    @app.post("/api/admin/reports/{report_id}")
    def admin_report_action(report_id: str, body: Moderation, x_admin_token: str | None = Header(None)):
        admin_ok(x_admin_token)
        r = next((x for x in store.reports if x["id"] == report_id), None)
        if r is None:
            raise HTTPException(404, detail="Nie znaleziono zgłoszenia")
        r["moderation"] = body.action
        r["moderated_at"] = datetime.now(timezone.utc).isoformat()
        r["moderation_note"] = re.sub(r"[\x00-\x1f<>]", "", body.note or "")[:300] or None
        store.save_reports()
        return {"id": report_id, "moderation": r["moderation"]}

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
