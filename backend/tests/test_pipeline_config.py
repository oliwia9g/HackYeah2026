"""Fakty z proweniencja, konfiguracja miasta, rejestr zrodel."""
import json

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from shapely.geometry import Point

from pipeline.common import ROOT, config_path, load_config
from pipeline.facts import make_osm_facts


def _pois():
    return gpd.GeoDataFrame({"wheelchair": ["yes", "yes", None], "check_date": ["2026-05-01", None, None]},
                            geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
                            index=pd.MultiIndex.from_tuples([("node", 1), ("node", 2), ("node", 3)]))


def test_fact_with_check_date_is_stronger_than_with_last_edit_only():
    f = make_osm_facts(_pois(), ["wheelchair"], 24, {"node/2": {"timestamp": "2025-03-01T10:00:00Z"}}).set_index("feature_id")
    assert f.loc["node/1", "confidence"] > f.loc["node/2", "confidence"]
    assert f.loc["node/2", "observed_basis"] == "last_edit"        # data edycji NIE jest potwierdzeniem dostepnosci


def test_no_tag_means_no_fact_not_accessible():
    f = make_osm_facts(_pois(), ["wheelchair"], 24, {})
    assert "node/3" not in set(f["feature_id"])


def test_every_fact_has_source_and_date():
    f = make_osm_facts(_pois(), ["wheelchair"], 24, {})
    for col in ("source", "license", "retrieved_at", "confidence", "status"):
        assert f[col].notna().all()


def test_default_city_config_is_krakow():
    cfg = load_config()
    assert cfg["city_name"] == "Kraków" and cfg["transit"]["gtfs"] and cfg["bbox"]["west"] < cfg["bbox"]["east"]


def test_city_config_switch_and_error(monkeypatch):
    monkeypatch.setenv("CITY_CONFIG", "nie_ma_takiego.yaml")
    with pytest.raises(FileNotFoundError):
        config_path()


def test_city_template_is_valid_yaml_with_required_keys():
    t = yaml.safe_load((ROOT / "cities" / "TEMPLATE.yaml").read_text("utf-8"))
    assert {"aoi", "city_name", "crs_metric", "paths", "osm", "transit"} <= set(t)
    assert t["paths"]["raw"] != load_config()["paths"]["raw"]         # kazde miasto ma wlasne katalogi danych


def test_every_used_source_has_license_status_and_limits():
    reg = yaml.safe_load((ROOT / "sources.yaml").read_text("utf-8"))
    for s in reg["used"]:
        assert s["license_status"] in ("potwierdzona", "do_potwierdzenia")
        for k in ("name", "license", "currency", "verification", "limitations"):
            assert s.get(k), f"{s['id']}: brak pola {k}"
