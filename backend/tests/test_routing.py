"""Silnik tras: profile, przeszkody ze wspolrzednymi, warianty, krawezniki."""
from tests.conftest import P


def alts(net, keys):
    return {r["id"]: r for r in net.route_alternatives(P[1], P[7], keys)}


def test_wheelchair_avoids_stairs(net):
    best = alts(net, ["wozek_inwalidzki"])["dostepna"]
    assert best["hazard_counts"].get("blokada", 0) == 0
    assert best["length_m"] >= 490            # objazd, nie skrot przez schody (175 m)


def test_shortest_route_is_honest_about_blockers(net):
    """Najkrotsza trasa idzie przez schody - dla wozka musi miec policzona BLOKADE, a nie byc przedstawiona jako OK."""
    short = alts(net, ["wozek_inwalidzki"]).get("najkrotsza")
    assert short is not None
    assert short["hazard_counts"].get("blokada", 0) >= 1
    assert short["length_m"] < 200


def test_hazards_have_coordinates_and_spoken_text(net):
    for r in alts(net, ["wozek_inwalidzki"]).values():
        for h in r["hazards"]:
            assert -180 <= h["lon"] <= 180 and -90 <= h["lat"] <= 90
            assert h["severity"] in ("blokada", "ostrzezenie", "brak_danych")
            assert h["spoken"] and h["text"]
            assert 0 <= h["at_m"] <= r["length_m"] + 1


def test_missing_kerb_data_is_not_presented_as_ok(net):
    hz = [h for r in alts(net, ["wozek_inwalidzki"]).values() for h in r["hazards"]]
    kerb = [h for h in hz if h["type"].startswith("krawezniki")]
    assert kerb, "przejscie z wysokim krawezkiem powinno byc zgloszone"


def test_recommended_route_exists_and_is_unique(net):
    rs = net.route_alternatives(P[1], P[7], ["wozek_inwalidzki"])
    assert sum(1 for r in rs if r["recommended"]) == 1


def test_different_profiles_give_different_results(net):
    wheel = alts(net, ["wozek_inwalidzki"])["dostepna"]["length_m"]
    blind = alts(net, ["niewidomy_slabowidzacy"])
    assert wheel >= min(r["length_m"] for r in blind.values())


def test_narration_is_announced_before_the_hazard(net):
    narrations = [n for r in alts(net, ["niewidomy_slabowidzacy"]).values() for n in r["narration"]]
    assert narrations, "dla niewidomego na tej trasie sa ostrzezenia do odczytania"
    for n in narrations:
        assert n["announce_at_m"] <= n["at_m"] and n["text"] and n["hazard_ids"]
