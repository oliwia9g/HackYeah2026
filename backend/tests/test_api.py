"""API end-to-end na danych syntetycznych (TestClient, bez serwera i bez sieci)."""
import os

from tests.conftest import P


# ---------- trasy ----------
def test_routes_returns_alternatives_and_one_recommended(client, q):
    r = client.get("/api/routes", params={**q, "profiles": "wozek_inwalidzki"})
    assert r.status_code == 200
    j = r.json()
    assert j["recommended"] and len(j["routes"]) >= 2
    p = j["routes"][0]["properties"]
    assert {"id", "length_m", "hazards", "hazard_counts", "narration"} <= set(p)


def test_routes_accept_custom_prefs_and_reject_bad_ones(client, q):
    assert client.get("/api/routes", params={**q, "prefs": "nostairs,kerb"}).status_code == 200
    bad = client.get("/api/routes", params={**q, "prefs": "zly"})
    assert bad.status_code == 422 and "dostepne_preferencje" in bad.json()["detail"]
    assert client.get("/api/routes", params={**q, "prefs": "incline:99"}).status_code == 422


def test_route_outside_area_is_rejected(client):
    r = client.get("/api/routes", params=dict(from_lon=0, from_lat=0, to_lon=P[7][0], to_lat=P[7][1], profiles="senior"))
    assert r.status_code == 422


def test_unknown_profile_is_rejected(client, q):
    assert client.get("/api/routes", params={**q, "profiles": "kosmita"}).status_code == 422


def test_plan_without_transit_data_still_gives_walking_route(client, q):
    r = client.get("/api/plan", params={**q, "profiles": "wozek_inwalidzki"})
    assert r.status_code == 200 and r.json()["walk_only"]


# ---------- miejsca, karta, fit, embed ----------
def test_place_card_has_provenance(client):
    c = client.get("/api/places/node/42").json()
    w = next(a for a in c["attributes"] if a["attribute"] == "wheelchair")
    assert w["status"] == "potwierdzone" and w["source"] and w["observed_at"] and w["license"]


def test_missing_data_is_never_shown_as_accessible(client):
    c = client.get("/api/places/node/t2").json()
    w = next(a for a in c["attributes"] if a["attribute"] == "wheelchair")
    assert w["status"] == "brak" and w["value"] is None and "nie oznacza" in w["note"]


def test_fit_verdicts(client):
    ok = client.get("/api/places/node/42", params={"prefs": "nostairs"}).json()["fit"]
    assert ok["verdict"] in ("pasuje", "prawdopodobnie_pasuje")
    unknown = client.get("/api/places/node/t2", params={"prefs": "nostairs"}).json()["fit"]
    assert unknown["verdict"] == "brak_danych"
    assert client.get("/api/places/node/42").json()["fit"] is None


def test_embed_is_script_free_html_with_csp(client):
    r = client.get("/embed/place/node/42", params={"prefs": "nostairs"})
    assert r.status_code == 200 and "<script" not in r.text and "<h1>" in r.text
    assert "frame-ancestors *" in r.headers["content-security-policy"]


def test_embed_escapes_html_in_names(client):
    r = client.get("/embed/place/node/xss")
    assert r.status_code == 200 and "<img" not in r.text and "&lt;img" in r.text


# ---------- zgloszenia i moderacja ----------
def test_report_is_unverified_and_conflicts_with_osm(client):
    r = client.post("/api/reports", json={"feature_id": "node/42", "attribute": "wheelchair", "value": "no", "comment": "Trzy stopnie"})
    assert r.status_code == 201 and r.json()["status"] == "niezweryfikowane" and r.json()["osm_edit_url"]
    w = next(a for a in client.get("/api/places/node/42").json()["attributes"] if a["attribute"] == "wheelchair")
    assert w["status"] == "sprzeczne"
    assert {v["status"] for v in w["versions"]} == {"potwierdzone", "niezweryfikowane"}


def test_report_validation(client):
    assert client.post("/api/reports", json={"feature_id": "node/999", "attribute": "wheelchair", "value": "no"}).status_code == 404
    assert client.post("/api/reports", json={"feature_id": "node/42", "attribute": "hack", "value": "no"}).status_code == 422


def test_report_html_is_stripped(client):
    client.post("/api/reports", json={"feature_id": "node/t2", "attribute": "wheelchair", "value": "no", "comment": "<script>alert(1)</script>Schody"})
    w = next(a for a in client.get("/api/places/node/t2").json()["attributes"] if a["attribute"] == "wheelchair")
    assert "<" not in (w["versions"][0]["comment"] or "")


def test_confirmation_counts_once_and_stays_unverified(client):
    rid = client.post("/api/reports", json={"feature_id": "node/t2", "attribute": "wheelchair", "value": "no"}).json()["id"]
    assert client.post(f"/api/reports/{rid}/confirm").json()["confirmations"] == 1
    assert client.post(f"/api/reports/{rid}/confirm").json()["confirmations"] == 1      # drugi raz z tego samego urzadzenia
    w = next(a for a in client.get("/api/places/node/t2").json()["attributes"] if a["attribute"] == "wheelchair")
    assert w["versions"][0]["status"] == "niezweryfikowane"


def test_report_rate_limit(client):
    codes = [client.post("/api/reports", json={"feature_id": "node/t2", "attribute": "wheelchair", "value": "no"}).status_code
             for _ in range(12)]
    assert codes.count(201) == 10 and 429 in codes


def test_moderation_requires_token_and_works(client, monkeypatch):
    rid = client.post("/api/reports", json={"feature_id": "node/t2", "attribute": "wheelchair", "value": "yes"}).json()["id"]
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/api/admin/reports").status_code == 404                      # bez tokenu na serwerze moderacja jest wylaczona
    monkeypatch.setenv("ADMIN_TOKEN", "tajne")
    assert client.get("/api/admin/reports", headers={"X-Admin-Token": "zly"}).status_code == 401
    h = {"X-Admin-Token": "tajne"}
    assert [x["id"] for x in client.get("/api/admin/reports", headers=h).json()] == [rid]
    assert client.post(f"/api/admin/reports/{rid}", json={"action": "zaakceptowane"}, headers=h).status_code == 200
    w = next(a for a in client.get("/api/places/node/t2").json()["attributes"] if a["attribute"] == "wheelchair")
    assert w["status"] == "potwierdzone"
    client.post(f"/api/admin/reports/{rid}", json={"action": "odrzucone"}, headers=h)
    w = next(a for a in client.get("/api/places/node/t2").json()["attributes"] if a["attribute"] == "wheelchair")
    assert w["status"] == "brak"
    assert client.post(f"/api/admin/reports/{rid}", json={"action": "usun"}, headers=h).status_code == 422


# ---------- najblizsze udogodnienia ----------
def test_nearest_uses_walking_network_and_profile(client):
    base = dict(lon=P[1][0], lat=P[1][1], kind="toaleta", max_m=2000)
    ped = client.get("/api/nearest", params=base).json()
    whl = client.get("/api/nearest", params={**base, "profiles": "wozek_inwalidzki"}).json()
    assert ped["results"] and whl["results"]
    assert whl["results"][0]["walk_m"] >= ped["results"][0]["walk_m"]
    acc = client.get("/api/nearest", params={**base, "accessible": True}).json()["results"]
    assert all(r["wheelchair"]["status"] == "potwierdzone" for r in acc) and acc


def test_nearest_unknown_kind_lists_valid_kinds(client):
    r = client.get("/api/nearest", params=dict(lon=P[1][0], lat=P[1][1], kind="xyz"))
    assert r.status_code in (404, 422) and "toaleta" in str(r.json())


# ---------- wiarygodnosc: zrodla, statystyki, braki, eksport, zdrowie ----------
def test_gaps_ranks_missing_and_stale_data(client):
    res = client.get("/api/gaps").json()["results"]
    ids = [r["id"] for r in res]
    assert "node/43" in ids                       # stare dane (2019) - do odswiezenia
    assert "node/42" not in ids                   # swieze i potwierdzone - nic do poprawy
    assert all(r["osm_note_url"] and r["powody"] for r in res)
    assert next(r for r in res if r["id"] == "node/43")["osm_edit_url"].endswith("node=43")
    assert res == sorted(res, key=lambda r: -r["priorytet"])


def test_export_csv_and_geojson_keep_provenance(client):
    csv_ = client.get("/api/export/places", params={"format": "csv"})
    assert csv_.status_code == 200 and "wheelchair_status" in csv_.text and "ODbL" in csv_.headers["x-attribution"]
    gj = client.get("/api/export/places", params={"format": "geojson"}).json()
    assert gj["type"] == "FeatureCollection" and "attribution" in gj
    pr = next(f["properties"] for f in gj["features"] if f["properties"]["id"] == "node/t2")
    assert pr["wheelchair_status"] == "brak" and pr["wheelchair_value"] is None


def test_stats_sources_health_meta(client):
    st = client.get("/api/stats").json()
    assert st["miejsca"]["razem"] == 9 and "uwaga" in st
    src = client.get("/api/sources").json()
    assert src["used"] and all("license_status" in s for s in src["used"])
    h = client.get("/api/health")
    assert h.status_code == 200 and h.headers["x-content-type-options"] == "nosniff" and h.headers["cache-control"] == "no-store"
    m = client.get("/api/meta").json()
    assert "preferencje" in m and "toaleta" in m["rodzaje_udogodnien"] and m["profiles"]


def test_outage_simulation_keeps_service_alive(client):
    client.post("/api/dev/outage", json={"on": True})
    assert client.get("/api/places/node/42").status_code == 200
    assert "dane_osm" in client.get("/api/health").json()["niedostepne"]
    client.post("/api/dev/outage", json={"on": False})


def test_demo_scenarios_cover_the_brief(client):
    client.post("/api/dev/seed")
    ids = {s["id"] for s in client.get("/api/demo/scenarios").json()["scenariusze"]}
    assert {"sprzeczne", "niepelne", "brak_danych", "awaria_zrodla", "tramwaj_na_zywo", "najblizsza_toaleta",
            "nalot_dronem", "tryb_prosty", "glos"} <= ids


def test_demo_scenario_urls_are_callable(client):
    """Kazdy adres z panelu demo musi dzialac (inaczej prezentacja zawiedzie na zywo)."""
    for s in client.get("/api/demo/scenarios").json()["scenariusze"]:
        if s.get("url"):
            r = client.get(s["url"])
            # 404/422/503: w testach nie ma adresow ani rozkladu (hermetyczna siatka), ale nigdy blad serwera 500
            assert r.status_code in (200, 404, 422, 503), (s["id"], r.status_code)


def test_voice_endpoint_returns_reply(client):
    j = client.get("/api/voice/command", params={"q": "pomoc"}).json()
    assert j["intent"] == "help" and j["reply"]


def test_kerbs_endpoint_explains_missing_pipeline_output(client):
    r = client.get("/api/kerbs")       # w testach nie ma pliku crossings.geojson
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert "fetch_osm" in r.json()["detail"]


def test_cors_and_security_headers(client):
    r = client.get("/api/meta", headers={"Origin": "https://front.example"})
    assert r.headers["access-control-allow-origin"] == "*" and r.headers["referrer-policy"] == "no-referrer"


# ---------- odmiana nazw (mowa: "z Rynku Glownego do Dworca Glownego") ----------
def test_geocode_understands_inflected_names(client):
    for said, want in [("Rynku Głównego", "Rynek Główny"), ("Dworca Głównego", "Dworzec Główny"), ("na Dworzec Główny", "Dworzec Główny")]:
        r = client.get("/api/geocode", params={"q": said, "limit": 1}).json()["results"]
        assert r and r[0]["label"] == want and not r[0]["fuzzy"], said


def test_voice_resolves_inflected_places_and_routes_end_to_end(client):
    j = client.get("/api/voice/command", params={"q": "trasa z Rynku Głównego do Dworca Głównego dla wózka"}).json()
    assert j["intent"] == "route" and j["resolved"] == {"from": "Rynek Główny", "to": "Dworzec Główny"}
    params = j["call"]["params"]
    assert params["profiles"] == "wozek_inwalidzki"
    assert client.get(j["call"]["endpoint"], params=params).status_code == 200


def test_unknown_place_by_voice_is_reported_not_guessed(client):
    j = client.get("/api/voice/command", params={"q": "z Rynku Głównego do Księżyca"}).json()
    assert j["intent"] == "not_found" and "ksi" in j["reply"].lower()
