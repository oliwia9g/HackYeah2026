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

from engine.profiles import PROFILES, merge_profiles
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
    def __init__(self, edges: pd.DataFrame, nodes: pd.DataFrame):
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

    @classmethod
    def from_files(cls, cfg: dict | None = None):
        cfg = cfg or load_config()
        raw = raw_dir(cfg)
        ep = raw / "edges_incline.pkl"
        if not ep.exists():
            print("UWAGA: brak edges_incline.pkl - nachylenie tylko z tagow OSM (uruchom pipeline.fetch_dem)")
            ep = raw / "edges.pkl"
        return cls(pd.read_pickle(ep), pd.read_pickle(raw / "nodes.pkl"))

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
                notes.append("schody")
            else:
                mult *= 1.8
                if "stairs_no_handrail" in w and not (e["handrail"] - {"no"}):
                    mult *= w["stairs_no_handrail"]
                    notes.append("schody bez potwierdzonej poręczy")
                else:
                    notes.append("schody")

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
                        notes.append(f"nachylenie {pct:.0f}% (limit {max_inc:.0f}%, źródło: {src})")
                    else:
                        notes.append(f"strome ({pct:.0f}%), ale to krótki odcinek z NMT - niepewne")
            elif max_inc is not None:
                uncertain = True
                notes.append("brak danych o nachyleniu")

        # nawierzchnia
        if "surface_rough" in w and kind != "schody":
            if e["surface"] & ROUGH_SURFACE or e["smoothness"] & BAD_SMOOTHNESS:
                mult *= w["surface_rough"]
                notes.append("nawierzchnia nierówna: " + ", ".join(sorted((e["surface"] & ROUGH_SURFACE) or e["smoothness"])))
            elif e["surface"] & MILD_SURFACE:
                mult *= w["surface_rough"] ** 0.5
                notes.append("nawierzchnia: " + ", ".join(sorted(e["surface"] & MILD_SURFACE)))
            elif not e["surface"] and not e["smoothness"] and kind == "chodnik":
                uncertain = True
                notes.append("brak danych o nawierzchni")

        # szerokosc
        if "min_width_m" in hard and e["width"] is not None and e["width"] < hard["min_width_m"]:
            blocked = True
            notes.append(f"szerokość {e['width']:.1f} m < {hard['min_width_m']} m")

        # przejscia: krawezniki, prowadzenie dotykowe, sygnal dzwiekowy
        if e["is_crossing"]:
            kerbs = nu["kerb"] | nv["kerb"] | e["kerb"]
            if "require_kerb" in hard:
                if kerbs & {"raised"}:
                    blocked = True
                    notes.append("krawężnik podwyższony (OSM)")
                elif kerbs:
                    if kerbs & {"rolled"}:
                        mult *= 1.3
                    notes.append("krawężnik: " + ", ".join(sorted(kerbs)) + " (OSM)")
                else:
                    uncertain = True
                    notes.append("brak danych o krawężniku")
            if "no_tactile_paving" in w:
                tactile = nu["tactile"] | nv["tactile"] | e["tactile"]
                if "yes" in tactile:
                    notes.append("prowadzenie dotykowe (OSM)")
                elif "no" in tactile:
                    mult *= w["no_tactile_paving"]
                    notes.append("brak prowadzenia dotykowego (OSM)")
                else:
                    mult *= w["no_tactile_paving"] ** 0.5
                    uncertain = True
                    notes.append("brak danych o prowadzeniu dotykowym")
            if "no_sound_signal" in w and (nu["signals"] or nv["signals"] or any("signal" in c for c in e["crossing_vals"])):
                if "yes" in (nu["sound"] | nv["sound"]):
                    notes.append("sygnalizacja dźwiękowa (OSM)")
                else:
                    mult *= w["no_sound_signal"]
                    notes.append("sygnalizator bez potwierdzonego sygnału dźwiękowego")

        if "unlit" in w and e["lit"] & {"no"}:
            mult *= w["unlit"]
            notes.append("brak oświetlenia")

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
        main = max(nx.weakly_connected_components(G), key=len) if G.number_of_nodes() else set()
        main_len = sum(d["length"] for a, b, d in G.edges(data=True) if a in main and b in main)
        all_len = sum(tot.values()) or 1.0
        stats = {
            "dlugosc_ok_km": round(tot[0] / 1000, 2), "dlugosc_niepewna_km": round(tot[1] / 1000, 2),
            "dlugosc_zablokowana_km": round(tot[2] / 1000, 2),
            "pct_zablokowane": round(100 * tot[2] / all_len, 1),
            "pct_w_glownej_spojnej": round(100 * main_len / (sum(d["length"] for *_, d in G.edges(data=True)) or 1), 1),
            "liczba_wysp": nx.number_weakly_connected_components(G),
        }
        v = View(prof["label"], list(keys), mode, G, status, notes, set(main), stats)
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
    def route(self, origin: tuple, dest: tuple, keys: list, mode: str = "warn"):
        v = self.view(keys, mode)
        if not v.main:
            return None
        s, t = self.nearest(*origin, v.main), self.nearest(*dest, v.main)
        try:
            path = nx.shortest_path(v.G, s, t, weight="cost")
        except nx.NetworkXNoPath:
            return None
        legs = [v.G[a][b] for a, b in zip(path, path[1:])]
        coords, groups = [], []
        for leg in legs:
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
            g["status"] = max(g["status"], leg["status"])
            for n in v.notes[leg["idx"]]:
                if n not in g["notes"]:
                    g["notes"].append(n)
        steps = []
        for g in groups:
            name, kind = g["key"]
            m = round(g["length"])
            if kind == "schody":
                text = f"Schody{' - ' + name if name else ''}, {m} m"
            elif kind == "przejscie":
                text = f"Przejście dla pieszych{' (' + name + ')' if name else ''}, {m} m"
            else:
                text = f"Idź {name or 'dalej'}, {m} m"
            if g["notes"]:
                text += " - " + "; ".join(g["notes"])
            if g["status"] == 1:
                text = "UWAGA (dane niepełne): " + text
            steps.append({"text": text, "length_m": m, "status": g["status"], "notes": g["notes"]})
        total = sum(leg["length"] for leg in legs)
        unc = sum(leg["length"] for leg in legs if leg["status"] == 1)
        speed = min([SPEED_KMH.get(k, BASE_SPEED_KMH) for k in keys]) if keys else BASE_SPEED_KMH
        return {
            "profile": v.label, "mode": mode, "length_m": round(total),
            "time_min": round(total / 1000 / speed * 60, 1),
            "pct_niepewne": round(100 * unc / total, 1) if total else 0.0,
            "steps": steps, "coords": coords,
        }

    # ---------- izochrona ----------
    def isochrone(self, origin: tuple, keys: list, minutes: float = 15, mode: str = "warn"):
        v = self.view(keys, mode)
        if not v.main:
            return None
        s = self.nearest(*origin, v.main)
        speed = min([SPEED_KMH.get(k, BASE_SPEED_KMH) for k in keys]) if keys else BASE_SPEED_KMH
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
              f"niepewne {s['dlugosc_niepewna_km']:5.2f} km | wysp: {s['liczba_wysp']}")

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

    print("\n=== IZOCHRONA 15 MIN od Dworca Głównego ===")
    iso_feats = []
    for keys in ([], *[[k] for k in PROFILES if k != "gluchy_niedoslyszacy"]):
        iso = net.isochrone(start, keys, 15, mode)
        if iso:
            print(f"{iso['profile']:34s} {iso['area_km2']:6.3f} km2, {iso['n_nodes']} węzłów")
            iso_feats.append({"type": "Feature", "geometry": iso.pop("geometry"), "properties": iso})
    with open(out / "isochrones.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": iso_feats}, f, ensure_ascii=False)

    net.export_edge_status(out / "edges_status.geojson")
    print("\nZapisano: demo_routes.geojson, isochrones.geojson, edges_status.geojson, profiles.json")


if __name__ == "__main__":
    main()
