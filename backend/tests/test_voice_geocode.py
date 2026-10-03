"""Polecenia glosowe i wyszukiwanie adresow (z literowkami)."""
from engine.geocode import Geocoder, parse_query
from engine.voice import parse_command


def E(t, s, n, lon, lat):
    return {"id": f"{t}/{s}{n}", "type": t, "street": s, "number": n, "lon": lon, "lat": lat}


GEO = Geocoder({"entries": [E("adres", "Floriańska", "12", 19.94, 50.063), E("adres", "Floriańska", "12A", 19.9401, 50.0631),
                            E("ulica", "Floriańska", None, 19.9405, 50.0633), E("ulica", "Plac Nowy", None, 19.945, 50.051),
                            E("adres", "Plac Nowy", "3", 19.9451, 50.0511)]})


def test_exact_address():
    assert GEO.search("Floriańska 12", 3)[0]["exact"]


def test_without_diacritics_and_prefix():
    assert GEO.search("ul. Florianska 12", 3)


def test_typo_is_tolerated():
    r = GEO.search("Florianka 12", 3)
    assert r and r[0]["fuzzy"]


def test_unknown_returns_nothing_instead_of_guessing():
    assert GEO.search("xyz", 3) == []


def test_parse_query_splits_number():
    assert parse_query("Św. Anny 5/2")[1] in ("5/2", "5")


import pytest


@pytest.mark.parametrize("text,to,profile", [
    ("trasa z Floriańska 10 do Dworzec Główny dla wózka", "dworzec główny", "wozek_inwalidzki"),
    ("jak dojść do Plant 5 na wózku inwalidzkim", "plant 5", "wozek_inwalidzki"),
    ("z Rynku do Dworca Głównego z dzieckiem", "dworca głównego", "wozek_dziecko"),
    ("z Rynku do Plant z wózkiem dziecięcym", "plant", "wozek_dziecko"),
    ("trasa z Rynku do dworca dla osoby niewidomej", "dworca", "niewidomy_slabowidzacy"),
    ("z rynku do plant w ciąży", "plant", "ciaza"),
])
def test_voice_route_command_strips_profile_phrase(text, to, profile):
    c = parse_command(text)
    assert c["intent"] == "route" and c["to_q"] == to and c["profiles"] == [profile]


def test_voice_plain_wozek_assumes_wheelchair_and_says_so():
    c = parse_command("z Rynku z wózkiem do Plant")
    assert c["profiles"] == ["wozek_inwalidzki"] and c["assumed"] and "dziecięc" in c["reply"]


def test_voice_from_gps_when_no_origin():
    c = parse_command("jak dojść do Plant 5")
    assert c["intent"] == "route" and c["from_gps"] and c["from_q"] is None


def test_voice_transit_and_help():
    assert parse_command("jakie są przystanki w pobliżu")["intent"] == "transit_nearby"
    assert parse_command("pomoc")["intent"] == "help"
    assert parse_command("")["intent"] == "help"


def test_deinflect_candidates_contain_base_forms():
    from engine.geocode import deinflect
    assert "rynek glowny" in deinflect("Rynku Głównego")
    assert "dworzec glowny" in deinflect("Dworca Głównego")
    assert "plac nowy" in deinflect("Placu Nowego")
    assert "florianska 10" in deinflect("Floriańskiej 10")      # numer domu zostaje
    assert "blonia" in deinflect("na Błonia")                   # przyimek odpada
    assert len(deinflect("Rynku Głównego Placu Nowego Dworca Głównego")) <= 30


def test_generic_destination_becomes_nearest_with_route():
    c = parse_command("jak dojść do apteki jestem seniorem")
    assert c["intent"] == "nearest" and c["kind"] == "apteka" and c["route_to_first"] and c["profiles"] == ["senior"]


@pytest.mark.parametrize("text,kind", [("gdzie jest najbliższa toaleta", "toaleta"), ("potrzebuję ławki", "lawka"),
                                       ("szukam toalety dla wózka", "toaleta"), ("gdzie jest winda", "winda"),
                                       ("najbliższa kawiarnia z wózkiem", "kawiarnia"), ("gdzie znajdę aptekę", "apteka")])
def test_voice_nearest_intent(text, kind):
    c = parse_command(text)
    assert c["intent"] == "nearest" and c["kind"] == kind


def test_where_am_i_is_not_swallowed_by_profile_words():
    assert parse_command("gdzie jestem")["intent"] == "where_am_i"
    assert parse_command("co jest wokół")["intent"] == "where_am_i"


@pytest.mark.parametrize("text,action", [("powtórz", "repeat"), ("dalej", "next_step"), ("stop", "stop"),
                                         ("jakie są przeszkody na trasie", "list_hazards"), ("ile jeszcze", "remaining"),
                                         ("tak", "confirm"), ("nie", "deny")])
def test_voice_client_actions(text, action):
    c = parse_command(text)
    assert c["intent"] == action and c["client_action"] == action


def test_voice_choice_by_number():
    assert parse_command("drugi")["index"] == 2 and parse_command("numer 3")["index"] == 3


def test_voice_preferences_and_profile_setting():
    c = parse_command("trasa z Rynku do Plant bez schodów dla wózka")
    assert c["intent"] == "route" and c["prefs"] == "nostairs" and c["to_q"] == "plant"
    s = parse_command("jestem niewidomy")
    assert s["intent"] == "set_profile" and s["profiles"] == ["niewidomy_slabowidzacy"]
    assert parse_command("bez schodów")["prefs"] == "nostairs"


def test_route_command_with_obstacle_word_is_not_a_client_action():
    assert parse_command("trasa z Rynku do Plant bez przeszkód")["intent"] == "route"
