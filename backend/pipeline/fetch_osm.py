"""Pobiera z OSM sieć pieszą + POI dla obszaru demo, robi audyt pokrycia tagów
i eksportuje GeoJSON-y dla frontu.

Uruchomienie (z katalogu backend/):
    python -m pipeline.fetch_osm            # audyt + eksport
    python -m pipeline.fetch_osm --audit    # tylko audyt (szybciej)
"""
from __future__ import annotations

import argparse
import json

import geopandas as gpd
import osmnx as ox
import pandas as pd

from pipeline.common import load_aoi, load_config, out_dir, query_aoi, raw_dir, with_overpass_fallback, write_geojson
from pipeline.facts import building_footprints, drop_noise_buildings, load_osm_meta, make_osm_facts

# Tagi krawędzi (chodniki, przejścia, schody), które chcemy mieć w grafie
EDGE_TAGS = [
    "highway", "footway", "sidewalk", "surface", "smoothness", "incline",
    "width", "kerb", "tactile_paving", "lit", "handrail", "ramp", "step_count",
    "crossing", "crossing:markings", "wheelchair", "bicycle", "check_date",
    "bridge", "tunnel", "layer",   # mosty/tunele: NMT nie nadaje sie do liczenia nachylen
]
# Tagi węzłów (przejścia i krawężniki często są na węzłach)
NODE_TAGS = [
    "highway", "kerb", "tactile_paving", "crossing", "crossing:island",
    "traffic_signals:sound", "traffic_signals:vibration", "wheelchair",
    "barrier", "check_date",
]


def configure_osmnx() -> None:
    ox.settings.use_cache = True
    ox.settings.log_console = False
    for t in EDGE_TAGS:
        if t not in ox.settings.useful_tags_way:
            ox.settings.useful_tags_way.append(t)
    for t in NODE_TAGS:
        if t not in ox.settings.useful_tags_node:
            ox.settings.useful_tags_node.append(t)


def clip_network(nodes, edges, aoi):
    """Zostawia tylko krawedzie, ktore maja cokolwiek wspolnego z AOI, i tylko ich wezly.
    Krawedz przecinajaca granice zostaje w calosci (inaczej w sieci powstalyby dziury przy brzegu)."""
    edges = edges[edges.geometry.intersects(aoi)]
    used = set(edges["u"]) | set(edges["v"])
    nodes = nodes[nodes["osmid"].isin(used)]
    return nodes, edges


def fetch_graph(cfg: dict):
    print("pobieram graf pieszy z OSM...")
    # retain_all=True: nie wycinamy małych odizolowanych kawałków, bo to też dane
    # query_aoi = uproszczony wielokat AOI (krotkie zapytania); truncate_by_edge: krawedzie przecinajace brzeg zostaja,
    # dzieki czemu siec nie urywa sie przed brzegiem
    G = with_overpass_fallback(
        ox.graph_from_polygon, query_aoi(cfg), network_type=cfg["osm"]["network_type"], retain_all=True, truncate_by_edge=True
    )
    nodes, edges = ox.graph_to_gdfs(G)
    nodes, edges = clip_network(nodes.reset_index(), edges.reset_index(), load_aoi(cfg))
    print(f"  węzły: {len(nodes)}, krawędzie: {len(edges)} (po przycięciu do AOI)")
    return G, nodes, edges


def within_aoi(gdf, cfg: dict):
    """Zostawia obiekty, ktorych punkt reprezentatywny lezy w AOI (Overpass bywa hojny na brzegu)."""
    if gdf.empty:
        return gdf
    return gdf[gdf.geometry.representative_point().within(load_aoi(cfg))]


def fetch_pois(cfg: dict) -> gpd.GeoDataFrame:
    print("pobieram POI z OSM...")
    pois = with_overpass_fallback(ox.features_from_polygon, query_aoi(cfg), cfg["osm"]["poi_tags"])
    pois = within_aoi(pois, cfg)
    pois = drop_noise_buildings(pois, cfg)
    print(f"  obiekty: {len(pois)}")
    return pois


def fetch_buildings(cfg: dict) -> gpd.GeoDataFrame:
    """Wszystkie obrysy budynkow w obszarze (do klikniecia w mape: adres i cechy budynku)."""
    print("pobieram obrysy budynkow z OSM...")
    b = with_overpass_fallback(ox.features_from_polygon, query_aoi(cfg), {"building": True})
    b = within_aoi(b, cfg)
    b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    print(f"  budynki: {len(b)}")
    return b


def fetch_crossings(cfg: dict) -> gpd.GeoDataFrame:
    """Przejścia i krawężniki jako osobne obiekty (węzły) do audytu i warstw."""
    tags = {"highway": ["crossing", "traffic_signals", "elevator", "steps"], "kerb": True}
    return within_aoi(with_overpass_fallback(ox.features_from_polygon, query_aoi(cfg), tags), cfg)


# ---------- AUDYT POKRYCIA ----------

def coverage(gdf: pd.DataFrame, cols: list[str]) -> dict:
    n = len(gdf)
    out = {}
    for c in cols:
        if n == 0 or c not in gdf.columns:
            out[c] = {"count": 0, "pct": 0.0}
        else:
            k = int(gdf[c].notna().sum())
            out[c] = {"count": k, "pct": round(100 * k / n, 1)}
    return out


def run_audit(edges, pois, crossings, cfg) -> dict:
    footways = edges[edges["highway"].astype(str).str.contains("footway|path|pedestrian|steps")]
    audit = {
        "bbox": cfg["bbox"],
        "edges_total": len(edges),
        "edges_footway_like": len(footways),
        "edges_tag_coverage": coverage(
            edges, ["surface", "smoothness", "incline", "width", "kerb", "lit", "tactile_paving"]
        ),
        "poi_total": len(pois),
        "poi_tag_coverage": coverage(
            pois,
            ["wheelchair", "wheelchair:description", "door:width", "toilets:wheelchair",
             "entrance", "check_date", "survey:date"],
        ),
        "crossings_total": len(crossings),
        "crossings_tag_coverage": coverage(
            crossings, ["kerb", "tactile_paving", "traffic_signals:sound", "traffic_signals:vibration"]
        ),
    }
    if "wheelchair" in pois.columns:
        audit["poi_wheelchair_values"] = pois["wheelchair"].value_counts().to_dict()
    return audit


def print_audit(a: dict) -> None:
    print("\n=== AUDYT POKRYCIA TAGÓW (obszar demo) ===")
    print(f"krawędzie: {a['edges_total']} (piesze: {a['edges_footway_like']})")
    for k, v in a["edges_tag_coverage"].items():
        print(f"  krawędzie z {k:15s} {v['count']:5d}  ({v['pct']}%)")
    print(f"POI: {a['poi_total']}")
    for k, v in a["poi_tag_coverage"].items():
        print(f"  POI z {k:25s} {v['count']:5d}  ({v['pct']}%)")
    if "poi_wheelchair_values" in a:
        print(f"  wartości wheelchair: {a['poi_wheelchair_values']}")
    print(f"przejścia/krawężniki: {a['crossings_total']}")
    for k, v in a["crossings_tag_coverage"].items():
        print(f"  z {k:28s} {v['count']:5d}  ({v['pct']}%)")


# ---------- EKSPORT ----------

def export(cfg, nodes, edges, pois, crossings, buildings=None) -> None:
    out = out_dir(cfg)
    raw = raw_dir(cfg)

    # obrys obszaru demo dla frontu (WGS84)
    import shapely
    from shapely.geometry import mapping
    (out / "area.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Obszar demo"}, "geometry": mapping(shapely.set_precision(load_aoi(cfg), 1e-6))}]},
        ensure_ascii=False), "utf-8")

    # surowe pliki (nie idą do gita)
    edges.to_pickle(raw / "edges.pkl")
    nodes.to_pickle(raw / "nodes.pkl")

    # krawędzie: tylko potrzebne kolumny + geometria
    keep = [c for c in EDGE_TAGS + ["u", "v", "key", "length", "geometry"] if c in edges.columns]
    write_geojson(edges[keep], out / "edges.geojson")

    # POI: punkty (dla obiektów powierzchniowych bierzemy centroid)
    pois_pts = pois.copy()
    pois_pts["geometry"] = pois_pts.geometry.representative_point()
    poi_cols = [c for c in ["name", "amenity", "shop", "tourism", "leisure", "building", "highway", "railway",
                            "public_transport", "wheelchair", "wheelchair:description", "door:width", "toilets:wheelchair",
                            "elevator", "check_date", "geometry"] if c in pois_pts.columns]
    poi_out = pois_pts[poi_cols].copy()
    # indeks to MultiIndex (typ, id); nazwy poziomow zalezą od wersji osmnx, wiec bierzemy po pozycji
    poi_out["feature_id"] = [f"{t}/{i}" for t, i in pois_pts.index]
    poi_out = poi_out.reset_index(drop=True)
    write_geojson(poi_out, out / "pois.geojson")

    # przejścia i krawężniki
    cross_pts = crossings.copy()
    cross_pts["geometry"] = cross_pts.geometry.representative_point()
    cross_pts["feature_id"] = [f"{t}/{i}" for t, i in cross_pts.index]
    write_geojson(cross_pts.reset_index(drop=True), out / "crossings.geojson")

    # fakty (tabela z proweniencją) - CSV + JSON dla frontu
    meta = load_osm_meta(raw)
    print(f"daty ostatniej edycji z Overpass: {len(meta)} obiektow" if meta
          else "brak osm_meta.json - daty tylko z check_date (uruchom pipeline.fetch_overpass_meta)")
    facts_src = pois
    if buildings is not None and len(buildings):
        # obrysy budynkow (klikanie w mape) + fakty z ich tagow (winda, rampa, toaleta...) takze dla budynkow spoza POI
        (out / "buildings.geojson").write_text(json.dumps(building_footprints(buildings, cfg), ensure_ascii=False), "utf-8")
        extra = buildings[~buildings.index.isin(pois.index)]
        facts_src = pd.concat([pois, extra]) if len(extra) else pois
        print(f"zapisano buildings.geojson ({len(buildings)} budynkow)")
    facts = make_osm_facts(facts_src, cfg["osm"]["fact_attributes"], cfg["freshness_months"], meta)
    facts.to_csv(out / "facts.csv", index=False)
    facts.to_json(out / "facts.json", orient="records", force_ascii=False)
    print(f"zapisano facts ({len(facts)} wierszy)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="tylko audyt, bez eksportu")
    args = ap.parse_args()

    cfg = load_config()
    configure_osmnx()

    _, nodes, edges = fetch_graph(cfg)
    pois = fetch_pois(cfg)
    crossings = fetch_crossings(cfg)
    buildings = fetch_buildings(cfg)

    audit = run_audit(edges, pois, crossings, cfg)
    print_audit(audit)
    with open(out_dir(cfg) / "audit.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    if not args.audit:
        export(cfg, nodes, edges, pois, crossings, buildings)


if __name__ == "__main__":
    main()
