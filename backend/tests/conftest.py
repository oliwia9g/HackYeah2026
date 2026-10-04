"""Wspolne dane testowe: mala, SYNTETYCZNA siatka pieszych polaczen (nie wymaga pobierania zadnych danych).

Uklad (wezly 1..7):  1 -[przejscie z wysokim krawezkiem]- 2 -[SCHODY]- 3 -- 7   (skrot, najkrotszy)
                     1 -- 4 -[kostka]- 5 -- 6 -- 7                               (objazd bez schodow)
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.routing import Net  # noqa: E402

P = {1: (19.940, 50.060), 2: (19.941, 50.060), 3: (19.942, 50.060), 4: (19.940, 50.0612),
     5: (19.9415, 50.0612), 6: (19.9435, 50.0612), 7: (19.942, 50.0603)}


def _edge(a, b, length, **kw):
    d = dict(u=a, v=b, key=0, length=length, geometry=LineString([P[a], P[b]]), highway="footway", name="Ul",
             surface="asphalt", incline_pct=1.0, incline_src="OSM")
    d.update(kw)
    return d


def build_net() -> Net:
    nodes = pd.DataFrame([{"osmid": k, "x": v[0], "y": v[1], "kerb": None} for k, v in P.items()])
    nodes.loc[nodes.osmid == 2, "kerb"] = "raised"
    rows = []

    def both(a, b, length, **kw):
        rows.extend([_edge(a, b, length, **kw), _edge(b, a, length, **kw)])

    both(1, 2, 70, footway="crossing", name="Przejscie")
    both(2, 3, 70, highway="steps", name="Schody Skrot")
    both(1, 4, 130, name="Objazd")
    both(4, 5, 130, surface="sett", name="Kostka")
    both(5, 6, 130, name="Objazd2")
    both(6, 7, 100, name="Objazd3")
    both(3, 7, 35, name="Koniec")
    return Net(pd.DataFrame(rows), nodes)


def _fact(fid, attr, value, status="potwierdzone", observed="2026-05-01"):
    return {"feature_id": fid, "attribute": attr, "value": value, "source": "OpenStreetMap", "source_url": None,
            "license": "ODbL", "retrieved_at": "2026-10-03", "observed_at": observed, "confidence": 0.8, "status": status}


def _poi(fid, lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"feature_id": fid, **props}}


@pytest.fixture(scope="session")
def net():
    return build_net()


def make_client(net, surveys=None, geocoder=None, buildings=None, extra_facts=None, transit=None):
    from fastapi.testclient import TestClient
    from api.main import create_app
    from engine.geocode import Geocoder
    from engine.realtime import Realtime
    from engine.surveys import Surveys
    from engine.buildings import Buildings
    from engine.transit import Transit
    from pipeline.common import load_config
    pois = {"features": [
        _poi("node/42", P[3][0], P[3][1] + 0.0001, name="Kawiarnia", amenity="cafe"),
        _poi("node/43", P[5][0], P[5][1], name="Apteka Pod Lipami", amenity="pharmacy"),
        _poi("node/t1", P[7][0] + 0.0001, P[7][1], name="Toaleta Rynek", amenity="toilets"),
        _poi("node/t2", P[3][0], P[3][1] + 0.0001, amenity="toilets"),
        _poi("node/rynek", P[2][0], P[2][1] + 0.0002, name="Rynek Główny", amenity="marketplace"),
        _poi("node/dworzec", P[6][0], P[6][1], name="Dworzec Główny", amenity="townhall"),
        _poi("node/lift1", P[3][0], P[3][1] + 0.0002, highway="elevator"),
        _poi("node/szpital", P[5][0] + 0.0002, P[5][1] + 0.0001, name="Szpital Miejski", building="hospital"),
        _poi("node/xss", P[2][0], P[2][1] + 0.0001, name="<img src=x onerror=alert(1)>", amenity="cafe"),
    ]}
    facts = [_fact("node/42", "wheelchair", "yes"), _fact("node/lift1", "wheelchair", "yes"),
             _fact("node/szpital", "elevator", "yes"), _fact("node/szpital", "ramp:wheelchair", "yes"), _fact("node/t1", "wheelchair", "yes"),
             _fact("node/43", "wheelchair", "yes", status="prawdopodobne", observed="2019-01-01")]
    facts = facts + (extra_facts or [])
    tmp = Path(tempfile.mkdtemp())
    # testy sa hermetyczne: bez prawdziwych plikow z data/raw (rozklad, adresy) i bez sieci (GTFS-RT)
    def no_network(name):
        raise RuntimeError("brak sieci w testach")
    app = create_app(net=net, pois_geojson=pois, facts=facts, cfg=load_config(), reports_path=tmp / "reports.json", signals_path=tmp / "signals.json", photos_dir=tmp / "photos",
                     transit=transit or Transit(None), geocoder=geocoder or Geocoder(None), realtime=Realtime(no_network),
                     surveys=surveys or Surveys(None), buildings=buildings or Buildings(None))
    return TestClient(app)


@pytest.fixture()
def client(net):
    return make_client(net)


@pytest.fixture()
def q():
    """Parametry zapytania trasy: od wezla 1 do wezla 7."""
    return dict(from_lon=P[1][0], from_lat=P[1][1], to_lon=P[7][0], to_lat=P[7][1])
