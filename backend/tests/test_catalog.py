"""Sztywne 6 grup + mozliwosc zdjecia (relax:) lub dodania (need:) pozycji."""
import pytest

from engine.profiles import PROFILES, active_items, build_profile, catalog, get_profile, merge_profiles
from tests.conftest import P


def test_six_fixed_groups_in_catalog():
    c = catalog()
    assert [g["key"] for g in c["grupy"]] == list(PROFILES) and len(c["grupy"]) == 6
    assert {"stairs", "toilet", "lift", "changing", "loop"} <= {i["id"] for i in c["pozycje"]}


def test_group_defaults_are_sensible():
    d = {g["key"]: set(g["domyslne"]) for g in catalog()["grupy"]}
    assert {"stairs", "kerb", "width"} <= d["wozek_inwalidzki"]
    assert "stairs" not in d["senior"] and "bench" in d["senior"]
    assert d["gluchy_niedoslyszacy"] == {"loop"}


def test_relax_removes_requirement_from_group():
    k = build_profile(["wozek_inwalidzki"], "relax:kerb,relax:width")
    p = get_profile(k[0])
    assert "require_kerb" not in p["hard"] and "min_width_m" not in p["hard"] and p["hard"]["forbid_steps"]
    assert "bez:" in p["label"]


def test_relax_does_not_change_the_base_group():
    build_profile(["wozek_inwalidzki"], "relax:stairs")
    assert PROFILES["wozek_inwalidzki"]["hard"]["forbid_steps"] is True


def test_need_adds_amenity_check():
    p = get_profile(build_profile([], "nostairs,need:toilet,need:changing")[0])
    assert {"toalety_dostepne", "przewijak"} <= set(p["needs"])


def test_errors():
    with pytest.raises(ValueError):
        build_profile([], "relax:kerb")                    # nie ma czego zdejmowac
    with pytest.raises(ValueError):
        build_profile(["senior"], "relax:xyz")
    with pytest.raises(ValueError):
        build_profile([], "need:xyz")


def test_relaxed_route_is_allowed_to_use_stairs(net):
    strict = {r["id"]: r for r in net.route_alternatives(P[1], P[7], build_profile(["wozek_inwalidzki"], None))}
    relaxed = {r["id"]: r for r in net.route_alternatives(P[1], P[7], build_profile(["wozek_inwalidzki"], "relax:stairs,relax:kerb"))}
    assert strict["dostepna"]["length_m"] > relaxed["dostepna"]["length_m"]


def test_catalog_endpoints(client, q):
    assert len(client.get("/api/catalog").json()["grupy"]) == 6
    r = client.get("/api/catalog/resolve", params={"profiles": "wozek_inwalidzki", "off": "kerb,width", "on": "changing"}).json()
    assert r["prefs"] == "need:changing,relax:kerb,relax:width"
    assert "kerb" not in r["aktywne"] and "changing" in r["aktywne"]
    res = client.get("/api/routes", params={**q, "profiles": "wozek_inwalidzki", "prefs": r["prefs"]})
    assert res.status_code == 200
    assert client.get("/api/catalog/resolve", params={"on": "nieznane"}).status_code == 422
    assert client.get("/api/catalog/resolve", params={"profiles": "senior", "on": "handrail"}).status_code == 422


def test_place_fit_respects_relax(client):
    attrs = lambda r: [x["attribute"] for x in r.json()["fit"]["checks"]]
    full = client.get("/api/places/node/42", params={"profile": "wozek_inwalidzki"})
    relaxed = client.get("/api/places/node/42", params={"profile": "wozek_inwalidzki", "prefs": "relax:width,relax:toilet"})
    assert full.status_code == 200 and relaxed.status_code == 200
    assert "door:width" in attrs(full) and "toilets:wheelchair" in attrs(full)
    assert "door:width" not in attrs(relaxed) and "toilets:wheelchair" not in attrs(relaxed)
    assert "wheelchair" in attrs(relaxed)
