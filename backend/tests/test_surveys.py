"""Naloty dronem: swiezosc danych, obserwacje na trasie, import CSV."""
from datetime import date, timedelta

import pytest
from shapely.geometry import box

from engine.surveys import Surveys
from pipeline.common import load_aoi, load_config
from pipeline.import_survey import parse_rows
from tests.conftest import P, make_client


def reg(days_ago, **kw):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return {"interval_months": 3, "surveys": [{"id": "n1", "type": "dron", "status": "wykonany", "date": d, **kw}]}


def surv(days_ago=10, obs=None, **kw):
    return Surveys(reg(days_ago, **kw), obs or [], load_aoi(load_config()))


# midpunkt odcinka 1-4 ("Objazd"), przez ktory idzie trasa dla wozka
OBS = [{"survey_id": "n1", "lon": 19.940, "lat": 50.0606, "type": "zastawiony_chodnik", "text": "samochody na chodniku"}]


def test_no_surveys_says_so_honestly(client):
    n = client.get("/api/places/node/42").json()["nalot"]
    assert n["has_survey"] is False and "Brak nalotu" in n["text"] and n["fresh"] is False


def test_fresh_and_stale_wording(net):
    fresh = make_client(net, surv(10)).get("/api/places/node/42").json()["nalot"]
    assert fresh["fresh"] and "świeże" in fresh["text"] and fresh["age_days"] == 10
    stale = make_client(net, surv(200)).get("/api/places/node/42").json()["nalot"]
    assert not stale["fresh"] and "nieaktualne" in stale["text"]


def test_demo_survey_is_always_labelled(net):
    t = make_client(net, surv(5, demo=True)).get("/api/places/node/42").json()["nalot"]["text"]
    assert "PRZYKŁADOWE" in t


def test_survey_outside_its_area_does_not_apply():
    # area=None oznacza caly obszar demo; tu "obszarem demo" jest box w innym miejscu swiata, wiec punkt w Krakowie nie jest objety
    assert Surveys(reg(5), [], box(0, 0, 1, 1)).status_at(19.94, 50.06)["has_survey"] is False


def test_route_gets_freshness_and_observation_hazards(net, q):
    c = make_client(net, surv(10, obs=OBS))
    j = c.get("/api/routes", params={**q, "profiles": "wozek_inwalidzki"}).json()
    best = next(f for f in j["routes"] if f["properties"]["id"] == "dostepna")["properties"]
    assert best["nalot"]["has_survey"] and best["nalot"]["coverage_fresh_pct"] == 100
    ob = [h for h in best["hazards"] if h["type"] == "obserwacja_nalotu"]
    assert len(ob) == 1 and ob[0]["severity"] == "ostrzezenie" and "nalotu" in ob[0]["text"] and ob[0]["observed_at"]
    assert 0 < ob[0]["at_m"] < best["length_m"]
    assert any(n["hazard_id"] == ob[0]["id"] for n in best["narration"])
    assert [h["at_m"] for h in best["hazards"]] == sorted(h["at_m"] for h in best["hazards"])
    base = make_client(net).get("/api/routes", params={**q, "profiles": "wozek_inwalidzki"}).json()
    base_best = next(f for f in base["routes"] if f["properties"]["id"] == "dostepna")["properties"]
    assert best["hazard_counts"]["ostrzezenie"] == base_best["hazard_counts"]["ostrzezenie"] + 1
    assert best["length_m"] == base_best["length_m"]                       # obserwacje NIE zmieniaja wyboru trasy


def test_observation_far_from_route_is_ignored(net, q):
    far = [{**OBS[0], "lon": 19.9435, "lat": 50.0600}]
    j = make_client(net, surv(10, obs=far)).get("/api/routes", params={**q, "profiles": "wozek_inwalidzki"}).json()
    assert all(h["type"] != "obserwacja_nalotu" for f in j["routes"] for h in f["properties"]["hazards"])


def test_surveys_endpoints(net):
    c = make_client(net, surv(10, obs=OBS))
    o = c.get("/api/surveys").json()
    assert o["last"]["fresh"] and o["observations_count"] == 1 and "nie widzi" in o["note"].lower()
    at = c.get("/api/surveys/at", params={"lon": P[1][0], "lat": P[1][1]}).json()
    assert at["has_survey"]
    assert c.get("/api/surveys/at", params={"lon": 0, "lat": 0}).status_code == 422
    gj = c.get("/api/surveys/observations").json()
    assert gj["features"][0]["properties"]["label"] == "Zastawiony chodnik"
    assert c.get("/api/stats").json()["nalot"]["last"]["has_survey"] is True
    assert "ostatni_nalot" in c.get("/api/meta").json()


def test_embed_shows_survey_line(net):
    r = make_client(net, surv(10)).get("/embed/place/node/42")
    assert "Ostatni nalot dronem" in r.text


def test_import_validates_rows():
    cfg = load_config()
    rows = [{"lon": "19.9373", "lat": "50.0617", "type": "remont", "text": "<b>wykop</b>"},
            {"lon": "x", "lat": "50", "type": "remont"},
            {"lon": "19.9373", "lat": "50.0617", "type": "ufo"},
            {"lon": "0", "lat": "0", "type": "remont"},
            {"lon": "19,9373", "lat": "50,0617", "type": "przeszkoda"}]
    ok, bad = parse_rows(rows, cfg, "n1")
    assert len(ok) == 2 and ok[0]["text"] == "wykop" and len(bad) == 3
    assert parse_rows([rows[0]], cfg, None)[0] == []                     # brak survey_id


def test_shipped_registry_marks_demo_entry():
    import yaml
    from pipeline.common import ROOT
    reg_ = yaml.safe_load((ROOT / "surveys.yaml").read_text("utf-8"))
    assert all(s.get("demo") for s in reg_["surveys"]), "kazdy wpis w dostarczonym surveys.yaml musi byc oznaczony jako demo"
