"""Silnik: ocena krawedzi per profil, trasa z opisem tekstowym, izochrona, status do mapy.

Wejscie (z backend/data/raw/, tworzone przez pipeline.fetch_osm i pipeline.fetch_dem):
    edges_incline.pkl (albo edges.pkl, jesli nie uruchomiono fetch_dem), nodes.pkl

Uruchomienie demo (z katalogu backend/):
    python -m engine.routing                # trasy + izochrony + status krawedzi -> public/data/
    python -m engine.routing --strict       # tryb "tylko pewne": krawedzie z brakami danych wykluczone

Statusy krawedzi:  0 = ok,  1 = niepewne (brak kluczowych danych, kara kosztu),  2 = zablokowane
Zasada: brak danych NIGDY nie oznacza "dostepne" - krawedz dostaje status 1 i ostrzezenie.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiPoint, mapping

from engine.profiles import PROFILES, merge_profiles, profile_speed
from pipeline.common import load_config, out_dir, raw_dir, write_geojson

# ---------- stale ----------
ROUGH_SURFACE = {"sett", "cobblestone", "unhewn_cobblestone", "gravel", "fine_gravel", "dirt",
                 "ground", "grass", "sand", "pebblestone", "mud", "unpaved", "earth"}
MILD_SURFACE = {"cobblestone:flattened", "compacted"}
BAD_SMOOTHNESS = {"bad", "very_bad", "horrible", "very_horrible", "impassable"}
FOOTWAY_LIKE = {"footway", "path", "pedestrian", "steps", "living_street", "track", "cycleway"}
SPEED_KMH = {"wozek_inwalidzki": 3.6, "wozek_dziecko": 4.0, "niewidomy_slabowidzacy": 3.5,
             "gluchy_niedoslyszacy": 4.8, "senior": 3.2, "ciaza": 3.6}
BASE_SPEED_KMH = 4.8
NMT_RELIABLE_MIN_LEN_M = 25.0   # krotsze odcinki: nachylenie z NMT zaszumione, nie blokujemy
REST_SNAP_M = 30.0              # lawka dalej niz tyle od najblizszego odcinka sieci nie jest brana pod uwage
REST_AMENITIES = {"bench"}      # miejsca odpoczynku z OSM (amenity=bench); leisure=picnic_table tez


# ---------- helpery do czyszczenia wartosci z OSM/pandas ----------
def clean(v):
    if isinstance(v, (list, tuple, set, np.ndarray)):
        v = [x for x in v if clean(x) is not None]
        return v or None
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and not v.strip():
        return None
    return v


def as_set(v) -> set:
    v = clean(v)
    if v is None:
        return set()
    if isinstance(v, list):
        return {str(x).lower() for x in v}
    return {str(v).lower()}


def to_float(v):
    v = clean(v)
    if isinstance(v, list):
        v = v[0]
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ".").replace("%", "").replace("m", "").strip())
    except ValueError:
        return None


def first_str(v):
    v = clean(v)
    if isinstance(v, list):
        v = v[0]
    return None if v is None else str(v)


class Note(str):
    """Uwaga o krawedzi: zwykly tekst + kod, waga i (opcjonalnie) wezel, ktorego dotyczy. Zgodna z kodem uzywajacym str.
    waga: blokada | ostrzezenie | brak_danych | info (info nie trafia na liste zagrozen)."""
    def __new__(cls, text: str, code: str = "info", sev: str = "info", node: int | None = None):
        o = super().__new__(cls, text)
        o.code, o.sev, o.node = code, sev, node
        return o


# Krawezniki wg definicji OSM (kerb=*): raised > 3 cm, lowered <= 3 cm, flush ~0 cm, rolled = pochyly/zaokraglony
KERB_PL = {
    "raised": ("wysoki", "wysoki krawężnik (powyżej 3 cm)"),
    "lowered": ("obnizony", "obniżony krawężnik (do 3 cm)"),
    "flush": ("rowny", "krawężnik zrównany z jezdnią"),
    "rolled": ("pochyly", "krawężnik pochyły (zaokrąglony)"),
    "no": ("brak", "bez krawężnika"),
}


def kerb_info(vals) -> dict:
    """vals: zbior/lista wartosci kerb z OSM -> {class, text, values}. Najgorsza wartosc wygrywa (raised > rolled > lowered > flush)."""
    vals = [v for v in as_set(vals)] if not isinstance(vals, (set, list, tuple)) else list(vals)
    known = [v for v in ("raised", "rolled", "lowered", "flush", "no") if v in vals]
    if not known:
        return {"class": "brak_danych", "text": "brak danych o krawężniku", "values": sorted(vals)}
    k = known[0]
    return {"class": KERB_PL[k][0], "text": KERB_PL[k][1], "values": sorted(vals)}


@dataclass
class View:
    """Wynik oceny sieci dla jednego profilu."""
    label: str
    keys: list
    mode: str
    G: nx.DiGraph
    status: list
    notes: list
    main: set = field(default_factory=set)
    stats: dict = field(default_factory=dict)


class Net:
    def __init__(self, edges: pd.DataFrame, nodes: pd.DataFrame, rest_points: list | None = None):
        self.xy, self.ntags = {}, {}
        for r in nodes.to_dict("records"):
            oid = int(r["osmid"])
            self.xy[oid] = (float(r["x"]), float(r["y"]))
            crossing = as_set(r.get("crossing"))
            self.ntags[oid] = {
                "kerb": as_set(r.get("kerb")),
                "tactile": as_set(r.get("tactile_paving")),
                "sound": as_set(r.get("traffic_signals:sound")),
                "signals": "traffic_signals" in as_set(r.get("highway")) or any("signal" in c for c in crossing),
            }
        has_incline_col = "incline_pct" in edges.columns
        self.edges = []
        for r in edges.to_dict("records"):
            hw, fw, cr = as_set(r.get("highway")), as_set(r.get("footway")), as_set(r.get("crossing"))
            is_crossing = "crossing" in fw or bool(cr)
            if "steps" in hw:
                kind = "schody"
            elif is_crossing:
                kind = "przejscie"
            elif hw & FOOTWAY_LIKE:
                kind = "chodnik"
            else:
                kind = "ulica"
            if has_incline_col:
                pct, src = to_float(r.get("incline_pct")), clean(r.get("incline_src"))
                if src == "brak":
                    pct = None
            else:
                pct = to_float(r.get("incline"))
                pct = abs(pct) if pct is not None else None
                src = "OSM" if pct is not None else None
            self.edges.append({
                "u": int(r["u"]), "v": int(r["v"]), "length": float(r.get("length") or 0.0),
                "geometry": r["geometry"], "name": first_str(r.get("name")), "kind": kind,
                "is_crossing": is_crossing, "crossing_vals": cr,
                "surface": as_set(r.get("surface")), "smoothness": as_set(r.get("smoothness")),
                "incline": pct, "incline_src": src, "kerb": as_set(r.get("kerb")),
                "tactile": as_set(r.get("tactile_paving")), "lit": as_set(r.get("lit")),
                "handrail": as_set(r.get("handrail")), "width": to_float(r.get("width")),
            })
        self._views: dict = {}
        self._compute_rest(rest_points)

    def _compute_rest(self, rest_points):
        """Dla kazdej krawedzi: odleglosc (po sieci pieszej) do najblizszej lawki z OSM -> e["rest_dist"] (m).
        Bez danych o lawkach rest_dist = None i regula odpoczynku w ogole nie dziala (nie karzemy za brak danych)."""
        self.rest_count = len(rest_points or [])
        self.rest_ready = self.rest_count > 0
        for e in self.edges:
            e["rest_dist"] = None
        if not self.rest_ready:
            return
        from pyproj import Transformer
        from shapely.ops import transform
        tr = Transformer.from_crs(4326, 2180, always_xy=True).transform
        geoms = [transform(tr, e["geometry"]) for e in self.edges]
        tree = shapely.STRtree(geoms)
        init: dict = {}
        for lon, lat in rest_points:
            pt = transform(tr, shapely.Point(lon, lat))
            hit = tree.query_nearest(pt, max_distance=REST_SNAP_M, all_matches=False)
            if len(hit) == 0:
                continue
            i = int(hit[0])
            e, g = self.edges[i], geoms[i]
            L = g.length or 1e-9
            s_ = g.project(pt)
            c0 = e["geometry"].coords[0]
            ux, uy = self.xy[e["u"]]
            vx, vy = self.xy[e["v"]]
            if (c0[0] - ux) ** 2 + (c0[1] - uy) ** 2 > (c0[0] - vx) ** 2 + (c0[1] - vy) ** 2:
                s_ = L - s_          # geometria biegnie od v do u
            k = e["length"] / L
            init[e["u"]] = min(init.get(e["u"], math.inf), s_ * k)
            init[e["v"]] = min(init.get(e["v"], math.inf), (L - s_) * k)
        H = nx.Graph()
        for e in self.edges:
            if not H.has_edge(e["u"], e["v"]) or H[e["u"]][e["v"]]["w"] > e["length"]:
                H.add_edge(e["u"], e["v"], w=e["length"])
        for n, d0 in init.items():
            H.add_edge("_lawka", n, w=d0)
        dist = nx.single_source_dijkstra_path_length(H, "_lawka", weight="w")
        for e in self.edges:
            e["rest_dist"] = min(dist.get(e["u"], math.inf), dist.get(e["v"], math.inf))

    @classmethod
    def from_files(cls, cfg: dict | None = None):
        cfg = cfg or load_config()
        raw = raw_dir(cfg)
        ep = raw / "edges_incline.pkl"
        if not ep.exists():
            print("UWAGA: brak edges_incline.pkl - nachylenie tylko z tagow OSM (uruchom pipeline.fetch_dem)")
            ep = raw / "edges.pkl"
        rest = []
        pf = out_dir(cfg) / "pois.geojson"
        if pf.exists():
            for f in json.loads(pf.read_text("utf-8")).get("features", []):
                p, g = f.get("properties", {}), f.get("geometry") or {}
                if g.get("type") == "Point" and (p.get("amenity") in REST_AMENITIES or p.get("leisure") == "picnic_table"):
                    rest.append((g["coordinates"][0], g["coordinates"][1]))
        else:
            print("UWAGA: brak pois.geojson - regula odpoczynku (lawki) wylaczona")
        return cls(pd.read_pickle(ep), pd.read_pickle(raw / "nodes.pkl"), rest)

    # ---------- ocena jednej krawedzi ----------
    def evaluate(self, e: dict, prof: dict):
        hard, w = prof["hard"], prof["weights"]
        notes, mult, blocked, uncertain = [], 1.0, False, False
        active = bool(hard or w)          # profil bez regul (np. niedoslyszacy) nic nie zmienia na trasie
        if not active:
            return 0, 1.0, notes
        nu, nv = self.ntags[e["u"]], self.ntags[e["v"]]
        kind, length = e["kind"], e["length"]

        # schody
        if kind == "schody":
            if hard.get("forbid_steps"):
                blocked = True
                notes.append(Note("schody", "schody", "blokada"))
            else:
                mult *= 1.8
                if "stairs_no_handrail" in w and not (e["handrail"] - {"no"}):
                    mult *= w["stairs_no_handrail"]
                    notes.append(Note("schody bez potwierdzonej poręczy", "schody_bez_poreczy", "ostrzezenie"))
                else:
                    notes.append(Note("schody", "schody", "ostrzezenie"))

        # nachylenie
        max_inc = hard.get("max_incline_pct")
        pct, src = e["incline"], e["incline_src"]
        if kind != "schody" and (max_inc is not None or "incline_per_pct" in w):
            if pct is not None:
                if "incline_per_pct" in w:
                    mult *= 1 + w["incline_per_pct"] * max(0.0, pct - 2.0)
                if max_inc is not None and pct > max_inc:
                    reliable = src == "OSM" or (src == "NMT" and length >= NMT_RELIABLE_MIN_LEN_M)
                    if reliable:
                        blocked = True
                        notes.append(Note(f"nachylenie {pct:.0f}% (limit {max_inc:.0f}%, źródło: {src})", "nachylenie", "blokada"))
                    else:
                        notes.append(Note(f"strome ({pct:.0f}%), ale to krótki odcinek z NMT - niepewne", "nachylenie_niepewne", "ostrzezenie"))
            elif max_inc is not None:
                uncertain = True
                notes.append(Note("brak danych o nachyleniu"))

        # nawierzchnia
        if "surface_rough" in w and kind != "schody":
            if e["surface"] & ROUGH_SURFACE or e["smoothness"] & BAD_SMOOTHNESS:
                mult *= w["surface_rough"]
                notes.append(Note("nawierzchnia nierówna: " + ", ".join(sorted((e["surface"] & ROUGH_SURFACE) or e["smoothness"])),
                                  "nawierzchnia", "ostrzezenie"))
            elif e["surface"] & MILD_SURFACE:
                mult *= w["surface_rough"] ** 0.5
                notes.append(Note("nawierzchnia: " + ", ".join(sorted(e["surface"] & MILD_SURFACE))))
            elif not e["surface"] and not e["smoothness"] and kind == "chodnik":
                uncertain = True
                notes.append(Note("brak danych o nawierzchni"))

        # szerokosc
        if "min_width_m" in hard and e["width"] is not None and e["width"] < hard["min_width_m"]:
            blocked = True
            notes.append(Note(f"szerokość {e['width']:.1f} m < {hard['min_width_m']} m", "waski", "blokada"))

        # przejscia: krawezniki, prowadzenie dotykowe, sygnal dzwiekowy
        if e["is_crossing"]:
            kerbs = nu["kerb"] | nv["kerb"] | e["kerb"]
            kn = e["u"] if "raised" in nu["kerb"] or (nu["kerb"] and not nv["kerb"]) else (e["v"] if nv["kerb"] else None)
            ki = kerb_info(kerbs)
            if "require_kerb" in hard:
                if kerbs & {"raised"}:
                    blocked = True
                    notes.append(Note("krawężnik podwyższony (OSM)", "krawezniki_wysoki", "blokada", kn))
                elif kerbs:
                    if kerbs & {"rolled"}:
                        mult *= 1.3
                        notes.append(Note("krawężnik pochyły (OSM)", "krawezniki_pochyly", "ostrzezenie", kn))
                    else:
                        notes.append(Note("krawężnik: " + ki["text"] + " (OSM)"))
                else:
                    uncertain = True
                    notes.append(Note("brak danych o krawężniku", "krawezniki_brak_danych", "brak_danych"))
            if "no_tactile_paving" in w:
                tactile = nu["tactile"] | nv["tactile"] | e["tactile"]
                if "yes" in tactile:
                    notes.append(Note("prowadzenie dotykowe (OSM)"))
                elif "no" in tactile:
                    mult *= w["no_tactile_paving"]
                    notes.append(Note("brak prowadzenia dotykowego (OSM)", "brak_prowadzenia", "ostrzezenie"))
                else:
                    mult *= w["no_tactile_paving"] ** 0.5
                    uncertain = True
                    notes.append(Note("brak danych o prowadzeniu dotykowym", "prowadzenie_brak_danych", "brak_danych"))
            if "no_sound_signal" in w and (nu["signals"] or nv["signals"] or any("signal" in c for c in e["crossing_vals"])):
                if "yes" in (nu["sound"] | nv["sound"]):
                    notes.append(Note("sygnalizacja dźwiękowa (OSM)"))
                else:
                    mult *= w["no_sound_signal"]
                    notes.append(Note("sygnalizator bez potwierdzonego sygnału dźwiękowego", "sygnalizator_bez_dzwieku", "ostrzezenie"))

        # odpoczynek: dlugi odcinek bez lawki (wg OSM) - tylko komfort, bez blokady i bez zmiany statusu
        if "long_segment_no_rest" in w and e.get("rest_dist") is not None and kind != "schody":
            lim = prof.get("bench_every_m", 300)
            if e["rest_dist"] > lim:
                mult *= w["long_segment_no_rest"]
                notes.append(Note(f"ponad {int(lim)} m od najbliższej ławki (wg OSM)", "brak_lawki", "ostrzezenie"))

        if "unlit" in w and e["lit"] & {"no"}:
            mult *= w["unlit"]
            notes.append(Note("brak oświetlenia", "brak_oswietlenia", "ostrzezenie"))

        status = 2 if blocked else (1 if uncertain else 0)
        if status == 1:
            mult *= prof.get("unknown_penalty", 1.0)
        return status, mult, notes

    # ---------- widok sieci dla profilu ----------
    def view(self, keys: list, mode: str = "warn") -> View:
        ck = (tuple(keys), mode)
        if ck in self._views:
            return self._views[ck]
        prof = merge_profiles(list(keys)) if keys else {"label": "Pieszy (bez ograniczeń)", "hard": {},
                                                          "weights": {}, "needs": [], "unknown_penalty": 1.0}
        G, status, notes = nx.DiGraph(), [], []
        tot = {0: 0.0, 1: 0.0, 2: 0.0}
        for i, e in enumerate(self.edges):
            st, mult, nts = self.evaluate(e, prof)
            status.append(st)
            notes.append(nts)
            tot[st] += e["length"]
            if st == 2 or (mode == "strict" and st == 1):
                continue
            cost = e["length"] * mult
            if G.has_edge(e["u"], e["v"]) and G[e["u"]][e["v"]]["cost"] <= cost:
                continue
            G.add_edge(e["u"], e["v"], cost=cost, length=e["length"], idx=i, status=st)
        comps = list(nx.weakly_connected_components(G))
        main = max(comps, key=len) if comps else set()
        # "wyspy dostepnosci" = kawalki sieci, ktore w sieci bazowej (pieszy bez ograniczen) naleza do
        # glownej spojnej, a po zastosowaniu profilu sa od niej odciete. Fragmenty OSM, ktore sa
        # rozlaczne juz w bazie (podworka, brzeg bbox), NIE sa liczone.
        base = self.view([], mode).main if keys else main
        islands = [c for c in comps if c is not main and (c & base)]
        cut_pct = round(100 * len(base - main) / (len(base) or 1), 1)
        main_len = sum(d["length"] for a, b, d in G.edges(data=True) if a in main and b in main)
        all_len = sum(tot.values()) or 1.0
        stats = {
            "dlugosc_ok_km": round(tot[0] / 1000, 2), "dlugosc_niepewna_km": round(tot[1] / 1000, 2),
            "dlugosc_zablokowana_km": round(tot[2] / 1000, 2),
            "pct_zablokowane": round(100 * tot[2] / all_len, 1),
            "pct_w_glownej_spojnej": round(100 * main_len / (sum(d["length"] for *_, d in G.edges(data=True)) or 1), 1),
            "wyspy_dostepnosci": len(islands), "odciete_wezly_pct": cut_pct,
        }
        v = View(prof["label"], list(keys), mode, G, status, notes, set(main), stats)
        if len(self._views) > 48:      # profile wlasne moga sie mnozyc - trzymamy ograniczony cache
            for k_ in [k_ for k_ in self._views if any(str(x).startswith("wlasne_") for x in k_[0])][:16]:
                self._views.pop(k_, None)
        self._views[ck] = v
        return v

    # ---------- najblizszy wezel ----------
    def nearest(self, lon: float, lat: float, nodes: set) -> int:
        ids = np.fromiter(nodes, dtype=np.int64)
        xs = np.array([self.xy[i][0] for i in ids])
        ys = np.array([self.xy[i][1] for i in ids])
        d = ((xs - lon) * math.cos(math.radians(lat))) ** 2 + (ys - lat) ** 2
        return int(ids[int(np.argmin(d))])

    def _oriented_coords(self, e: dict):
        coords = list(e["geometry"].coords)
        ux, uy = self.xy[e["u"]]
        if (coords[0][0] - ux) ** 2 + (coords[0][1] - uy) ** 2 > (coords[-1][0] - ux) ** 2 + (coords[-1][1] - uy) ** 2:
            coords.reverse()
        return coords

    # ---------- trasa ----------
    HAZARD_SEV_ORDER = {"blokada": 0, "ostrzezenie": 1, "brak_danych": 2}
    HAZARD_SPOKEN = {
        "schody": "schody", "schody_bez_poreczy": "schody bez potwierdzonej poręczy",
        "nachylenie": "stromy odcinek", "nachylenie_niepewne": "możliwy stromy odcinek",
        "nawierzchnia": "nierówna nawierzchnia", "waski": "wąskie przejście",
        "krawezniki_wysoki": "wysoki krawężnik", "krawezniki_pochyly": "pochyły krawężnik",
        "krawezniki_brak_danych": "krawężnik bez danych o wysokości",
        "brak_prowadzenia": "brak prowadzenia dotykowego", "prowadzenie_brak_danych": "brak danych o prowadzeniu dotykowym",
        "sygnalizator_bez_dzwieku": "sygnalizator bez potwierdzonego sygnału dźwiękowego",
        "brak_lawki": "długi odcinek bez ławki", "brak_oswietlenia": "brak oświetlenia",
    }

    def _hazards(self, legs: list, ev: View) -> list:
        """Lista zagrozen na trasie z lokalizacja (lon/lat) i odlegloscia od startu. Kolejne krawedzie z tym samym
        zagrozeniem (np. dluga kostka) sa laczone w jedno. Sprawdza wg profilu `ev`, niezaleznie od tego, jak trase wyznaczono."""
        out, last_by_code, seen_nodes, pos = [], {}, set(), 0.0
        for k, leg in enumerate(legs):
            e = self.edges[leg["idx"]]
            for n in ev.notes[leg["idx"]]:
                sev = getattr(n, "sev", "info")
                if sev not in self.HAZARD_SEV_ORDER:
                    continue
                code = n.code
                if n.node is not None:          # zagrozenie w punkcie (krawezniki): jedno na wezel
                    if n.node in seen_nodes:
                        continue
                    seen_nodes.add(n.node)
                    lon, lat = self.xy[n.node]
                    out.append({"type": code, "severity": sev, "text": str(n), "lon": lon, "lat": lat,
                                "at_m": round(pos + (0 if n.node == e["u"] else e["length"])), "length_m": 0,
                                "street": e["name"], "kind": e["kind"]})
                    continue
                prev = last_by_code.get(code)
                if prev is not None and prev[0] == k - 1:   # ciagle od poprzedniej krawedzi
                    prev[1]["length_m"] += round(e["length"])
                    last_by_code[code] = (k, prev[1])
                    continue
                mid = e["geometry"].interpolate(0.5, normalized=True)
                h = {"type": code, "severity": sev, "text": str(n), "lon": mid.x, "lat": mid.y,
                     "at_m": round(pos), "length_m": round(e["length"]), "street": e["name"], "kind": e["kind"]}
                out.append(h)
                last_by_code[code] = (k, h)
            pos += e["length"]
        out.sort(key=lambda h: (h["at_m"], self.HAZARD_SEV_ORDER[h["severity"]]))
        for i, h in enumerate(out, 1):
            h["id"] = i
            what = self.HAZARD_SPOKEN.get(h["type"], h["text"])
            where = f" na ulicy {h['street']}" if h["street"] and h["kind"] in ("chodnik", "ulica") else ""
            h["spoken"] = what[:1].upper() + what[1:] + where
            h["source"] = "OSM/NMT" if h["type"] in ("nachylenie", "nachylenie_niepewne") else "OSM"
            h["lon"], h["lat"] = round(h["lon"], 6), round(h["lat"], 6)
        return out

    @staticmethod
    def _ahead(m: int) -> str:
        """Zaokraglona odleglosc do komunikatu glosowego."""
        if m < 15:
            return "teraz"
        step = 10 if m < 100 else 50
        return f"za {int(round(m / step) * step)} metrów"

    def route(self, origin: tuple, dest: tuple, keys: list, mode: str = "warn", route_keys: list | None = None):
        """origin/dest = (lon, lat). Trase WYZNACZA widok (route_keys, mode); zagrozenia i kroki OCENIA profil `keys`.
        Zwykle route_keys = keys. Dla trasy "najkrotszej" route_keys=[] - widac wtedy, co ja czeka na drodze."""
        rv = self.view(keys if route_keys is None else route_keys, mode)
        ev = self.view(keys, mode if route_keys is None else "warn")
        if not rv.main:
            return None
        s, t = self.nearest(*origin, rv.main), self.nearest(*dest, rv.main)
        try:
            path = nx.shortest_path(rv.G, s, t, weight="cost")
        except nx.NetworkXNoPath:
            return None
        legs = [rv.G[a][b] for a, b in zip(path, path[1:])]
        st_ev = [ev.status[leg["idx"]] for leg in legs]     # lokalnie: widoki sa wspoldzielone miedzy watkami API
        coords, groups = [], []
        for leg, st in zip(legs, st_ev):
            e = self.edges[leg["idx"]]
            c = self._oriented_coords(e)
            coords.extend(c if not coords else c[1:])
            gkey = (e["name"], e["kind"])
            if groups and groups[-1]["key"] == gkey:
                g = groups[-1]
            else:
                g = {"key": gkey, "length": 0.0, "status": 0, "notes": []}
                groups.append(g)
            g["length"] += e["length"]
            g["status"] = max(g["status"], st)
            for n in ev.notes[leg["idx"]]:
                if n not in g["notes"]:
                    g["notes"].append(n)
        steps = []
        cum = 0.0
        for g in groups:
            name, kind = g["key"]
            m = round(g["length"])
            start_m = round(cum)
            cum += g["length"]
            if kind == "schody":
                text = f"Schody{' - ' + name if name else ''}, {m} m"
            elif kind == "przejscie":
                text = f"Przejście dla pieszych{' (' + name + ')' if name else ''}, {m} m"
            else:
                text = f"Idź {name or 'dalej'}, {m} m"
            if g["notes"]:
                text += " - " + "; ".join(str(n) for n in g["notes"])
            if g["status"] == 2:
                text = "PRZESZKODA: " + text
            elif g["status"] == 1:
                text = "UWAGA (dane niepełne): " + text
            steps.append({"text": text, "length_m": m, "status": g["status"], "notes": [str(n) for n in g["notes"]],
                          "name": name, "kind": kind, "start_m": start_m})
        total = sum(leg["length"] for leg in legs)
        unc = sum(leg["length"] for leg, st in zip(legs, st_ev) if st == 1)
        blk = sum(leg["length"] for leg, st in zip(legs, st_ev) if st == 2)
        speed = min([profile_speed(k, BASE_SPEED_KMH, SPEED_KMH) for k in keys]) if keys else BASE_SPEED_KMH
        rd = [self.edges[leg["idx"]]["rest_dist"] for leg in legs if self.edges[leg["idx"]].get("rest_dist") is not None]
        hazards = self._hazards(legs, ev)
        counts = {k: sum(1 for h in hazards if h["severity"] == k) for k in self.HAZARD_SEV_ORDER}
        narration, by_pos = [], {}
        for h in hazards:      # kilka zagrozen w tym samym miejscu (np. kostka + brak danych o krawezniku) = jeden komunikat
            g = by_pos.get(h["at_m"])
            if g is None:
                g = {"at_m": h["at_m"], "announce_at_m": max(0, h["at_m"] - 30), "lon": h["lon"], "lat": h["lat"],
                     "text": h["spoken"], "severity": h["severity"], "hazard_id": h["id"], "hazard_ids": [h["id"]]}
                by_pos[h["at_m"]] = g
                narration.append(g)
            else:
                low = h["spoken"][:1].lower() + h["spoken"][1:]
                g["text"] += "; " + low
                g["hazard_ids"].append(h["id"])
                if self.HAZARD_SEV_ORDER[h["severity"]] < self.HAZARD_SEV_ORDER[g["severity"]]:
                    g["severity"] = h["severity"]
        return {
            "max_do_lawki_m": round(max(rd)) if rd else None, "lawki_w_danych": self.rest_count,
            "profile": ev.label, "mode": mode, "length_m": round(total),
            "time_min": round(total / 1000 / speed * 60, 1),
            "pct_niepewne": round(100 * unc / total, 1) if total else 0.0,
            "pct_przeszkody": round(100 * blk / total, 1) if total else 0.0,
            "steps": steps, "coords": coords, "hazards": hazards, "hazard_counts": counts,
            "narration": narration, "path": tuple(leg["idx"] for leg in legs),
        }

    def route_alternatives(self, origin: tuple, dest: tuple, keys: list) -> list:
        """Do trzech wariantow trasy z listami zagrozen (wszystkie oceniane profilem `keys`):
        - dostepna:    tylko odcinki z pelnymi danymi i bez barier (tryb strict) - najbezpieczniejsza, moze byc dluzsza
        - zrownowazona: omija bariery, dopuszcza odcinki z brakami danych (z kara) - domyslna
        - najkrotsza:  ignoruje bariery profilu - pokazuje, co czeka na najkrotszej drodze
        Identyczne przebiegi sa scalane (wariant zachowuje liste `tez_jako`). Zwraca liste od najlepszej."""
        specs = ([("dostepna", "Najbardziej dostępna (tylko pewne odcinki)", "strict", None),
                  ("zrownowazona", "Zrównoważona (omija bariery)", "warn", None),
                  ("najkrotsza", "Najkrótsza (pokazuje przeszkody)", "warn", [])] if keys else
                 [("najkrotsza", "Najkrótsza", "warn", [])])
        res = []
        for rid, label, mode, rk in specs:
            r = self.route(origin, dest, keys, mode, route_keys=rk)
            if r is None:
                continue
            twin = next((x for x in res if x["path"] == r["path"]), None)
            if twin is not None:
                twin["tez_jako"].append(label)
                continue
            r.update({"id": rid, "label": label, "tez_jako": []})
            res.append(r)
        if not res:
            return []
        shortest = min(r["length_m"] for r in res)
        for r in res:
            r["extra_m"] = r["length_m"] - shortest
            r["extra_pct"] = round(100 * r["extra_m"] / shortest, 1) if shortest else 0.0
        # polecana = bez przeszkod, a z nich najmniej zagrozen i najkrotsza
        res.sort(key=lambda r: (r["hazard_counts"]["blokada"], r["hazard_counts"]["ostrzezenie"] + r["hazard_counts"]["brak_danych"], r["length_m"]))
        res[0]["recommended"] = True
        for r in res[1:]:
            r["recommended"] = False
        return res

    # ---------- zasieg pieszy: odleglosc SIECIA (nie w linii prostej) do wielu punktow ----------
    def walk_distances(self, origin: tuple, targets: list, keys: list, mode: str = "warn", cutoff_m: float = 1500,
                       max_snap_m: float = 60) -> list:
        """targets = [(lon, lat), ...]. Zwraca liste (indeks_celu, odleglosc_m_po_sieci) dla celow osiagalnych w cutoff_m,
        wg ograniczen profilu (zablokowane odcinki sa pomijane). Cel dalej niz max_snap_m od sieci jest pomijany."""
        v = self.view(keys, mode)
        if not v.main or not targets:
            return []
        s = self.nearest(*origin, v.main)
        dist = nx.single_source_dijkstra_path_length(v.G, s, cutoff=cutoff_m, weight="length")
        ids = np.fromiter(dist.keys(), dtype=np.int64)
        xs = np.array([self.xy[i][0] for i in ids])
        ys = np.array([self.xy[i][1] for i in ids])
        d0 = np.array([dist[i] for i in ids])
        out = []
        for k, (lon, lat) in enumerate(targets):
            dx = (xs - lon) * 111_320 * math.cos(math.radians(lat))
            dy = (ys - lat) * 110_540
            snap = np.hypot(dx, dy)
            tot = np.where(snap <= max_snap_m, d0 + snap, np.inf)   # tylko wezly blisko obiektu
            j = int(np.argmin(tot))
            if tot[j] <= cutoff_m:
                out.append((k, float(tot[j])))
        return out

    # ---------- izochrona ----------
    def isochrone(self, origin: tuple, keys: list, minutes: float = 15, mode: str = "warn",
                  equal_speed: bool = True):
        """equal_speed=True: ta sama predkosc dla wszystkich profili, zeby kurczenie sie obszaru
        wynikalo WYLACZNIE z barier, a nie z zalozonej wolniejszej chodzy."""
        v = self.view(keys, mode)
        if not v.main:
            return None
        s = self.nearest(*origin, v.main)
        if equal_speed or not keys:
            speed = BASE_SPEED_KMH
        else:
            speed = min(profile_speed(k, BASE_SPEED_KMH, SPEED_KMH) for k in keys)
        limit = minutes / 60 * speed * 1000
        dist = nx.single_source_dijkstra_path_length(v.G, s, cutoff=limit + 0.5, weight="length")  # +0.5 m: tolerancja zaokraglen
        pts = [self.xy[n] for n in dist]
        if len(pts) < 4:
            return None
        hull = shapely.concave_hull(MultiPoint(pts), ratio=0.25)
        area = gpd.GeoSeries([hull], crs="EPSG:4326").to_crs("EPSG:2180").area.iloc[0] / 1e6
        return {"profile": v.label, "minutes": minutes, "speed_kmh": speed,
                "n_nodes": len(dist), "area_km2": round(float(area), 3), "geometry": mapping(hull)}

    # ---------- eksport statusu krawedzi do kolorowania mapy ----------
    def export_edge_status(self, out_path):
        order = list(PROFILES)
        views = [self.view([k]) for k in order]
        merged: dict = {}
        for i, e in enumerate(self.edges):
            code = [str(v.status[i]) for v in views]
            pair = (min(e["u"], e["v"]), max(e["u"], e["v"]))
            if pair in merged:
                old = merged[pair]["s"]
                merged[pair]["s"] = [max(a, b) for a, b in zip(old, code)]
            else:
                merged[pair] = {"s": code, "name": e["name"], "kind": e["kind"], "geometry": e["geometry"],
                                "notes": {k: v.notes[i] for k, v in zip(order, views) if v.notes[i]}}
        gdf = gpd.GeoDataFrame(
            {"name": [m["name"] for m in merged.values()], "kind": [m["kind"] for m in merged.values()],
             "s": ["".join(m["s"]) for m in merged.values()],
             "notes": [json.dumps(m["notes"], ensure_ascii=False) for m in merged.values()]},
            geometry=[m["geometry"] for m in merged.values()], crs="EPSG:4326")
        write_geojson(gdf, out_path)
        meta = [{"key": k, "label": PROFILES[k]["label"], "needs": PROFILES[k]["needs"]} for k in order]
        with open(out_path.parent / "profiles.json", "w", encoding="utf-8") as f:
            json.dump({"order": meta, "status_legend": {"0": "ok", "1": "niepewne (brak danych)", "2": "zablokowane"}},
                      f, ensure_ascii=False, indent=2)

    # ---------- ranking barier ----------
    def barrier_ranking(self, keys: list, top: int = 15, mode: str = "warn") -> list:
        """Ktore zablokowane odcinki odcinaja najwiecej sieci od glownej spojnej?
        Dla kazdej "wyspy dostepnosci" wybieramy najkrotszy blokujacy odcinek (najtanszy do naprawy)."""
        v = self.view(keys, mode)
        base = self.view([], mode).main
        comps = list(nx.weakly_connected_components(v.G))
        if not comps:
            return []
        main = max(comps, key=len)
        comp_of = {n: i for i, c in enumerate(comps) for n in c}
        main_id = comp_of[next(iter(main))]
        comp_len: dict = {}
        for a, _b, d in v.G.edges(data=True):
            comp_len[comp_of[a]] = comp_len.get(comp_of[a], 0.0) + d["length"]
        best: dict = {}
        for i, e in enumerate(self.edges):
            if v.status[i] != 2:
                continue
            a, b = comp_of.get(e["u"]), comp_of.get(e["v"])
            if a is None or b is None or a == b or main_id not in (a, b):
                continue
            isl = b if a == main_id else a
            gain = len(comps[isl] & base)
            if gain < 5:
                continue
            if isl not in best or e["length"] < best[isl][1]["length"]:
                best[isl] = (i, e, gain)
        rows = []
        for isl, (i, e, gain) in best.items():
            mid = e["geometry"].interpolate(0.5, normalized=True)
            rows.append({
                "profil": v.label, "ulica": e["name"] or "(bez nazwy)", "rodzaj": e["kind"],
                "powod": "; ".join(v.notes[i]) or "-", "odcina_wezlow": gain,
                "odcina_m_sieci": round(comp_len.get(isl, 0.0) / 2),   # krawedzie sa dwukierunkowe
                "lon": round(mid.x, 6), "lat": round(mid.y, 6)})
        rows.sort(key=lambda r: -r["odcina_m_sieci"])
        return rows[:top]


# ---------- demo ----------
DEMO = {"Dworzec Główny": (19.9477, 50.0680), "Rynek Główny": (19.9373, 50.0617),
        "Plac Nowy (Kazimierz)": (19.9446, 50.0516), "Wawel": (19.9353, 50.0540)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help='tryb "tylko pewne"')
    args = ap.parse_args()
    mode = "strict" if args.strict else "warn"

    cfg = load_config()
    net = Net.from_files(cfg)
    out = out_dir(cfg)
    print(f"krawędzie: {len(net.edges)}, węzły: {len(net.xy)}")

    print("\n=== STATYSTYKI SIECI PER PROFIL ===")
    for k in PROFILES:
        s = net.view([k], mode).stats
        print(f"{PROFILES[k]['label']:34s} zablokowane {s['pct_zablokowane']:5.1f}% | "
              f"niepewne {s['dlugosc_niepewna_km']:5.2f} km | odcięte węzły {s['odciete_wezly_pct']:4.1f}% "
              f"| wyspy dostępności: {s['wyspy_dostepnosci']}")

    start, goal = DEMO["Dworzec Główny"], DEMO["Plac Nowy (Kazimierz)"]
    feats = []
    print("\n=== TRASA: Dworzec Główny -> Plac Nowy ===")
    for keys in ([], ["wozek_inwalidzki"], ["wozek_dziecko"], ["niewidomy_slabowidzacy"], ["senior"]):
        r = net.route(start, goal, keys, mode)
        label = net.view(keys, mode).label
        if r is None:
            print(f"{label:34s} BRAK TRASY")
            continue
        print(f"{label:34s} {r['length_m']:5d} m, {r['time_min']:4.1f} min, niepewne {r['pct_niepewne']}%")
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": r["coords"]},
                      "properties": {k: r[k] for k in ("profile", "mode", "length_m", "time_min", "pct_niepewne")}
                                    | {"steps": r["steps"]}})
    with open(out / "demo_routes.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)

    print("\n=== IZOCHRONA 15 MIN od Dworca Głównego (ta sama prędkość dla wszystkich = efekt samych barier) ===")
    iso_feats = []
    for keys in ([], *[[k] for k in PROFILES if k != "gluchy_niedoslyszacy"]):
        iso = net.isochrone(start, keys, 15, mode)
        if iso:
            print(f"{iso['profile']:34s} {iso['area_km2']:6.3f} km2, {iso['n_nodes']} węzłów")
            iso_feats.append({"type": "Feature", "geometry": iso.pop("geometry"), "properties": iso})
    with open(out / "isochrones.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": iso_feats}, f, ensure_ascii=False)

    print("\n=== RANKING BARIER (co najbardziej odcina sieć od głównej) ===")
    bar_feats = []
    for k in ("wozek_inwalidzki", "wozek_dziecko", "senior"):
        rows = net.barrier_ranking([k], top=15, mode=mode)
        print(f"-- {PROFILES[k]['label']}: {len(rows)} barier odcinających wyspy")
        for rank, r in enumerate(rows, 1):
            if rank <= 5:
                print(f"   {rank}. {r['ulica']} ({r['rodzaj']}): odcina ok. {r['odcina_m_sieci']} m sieci "
                      f"/ {r['odcina_wezlow']} węzłów - {r['powod']}")
            bar_feats.append({"type": "Feature",
                              "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                              "properties": {**{kk: vv for kk, vv in r.items() if kk not in ("lon", "lat")},
                                             "profil_klucz": k, "ranking": rank}})
    with open(out / "barriers.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": bar_feats}, f, ensure_ascii=False)

    net.export_edge_status(out / "edges_status.geojson")
    print("\nZapisano: demo_routes.geojson, isochrones.geojson, barriers.geojson, edges_status.geojson, profiles.json")


if __name__ == "__main__":
    main()
