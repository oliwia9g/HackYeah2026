"""Wlasne preferencje (bez nazw grup) i walidacja."""
import pytest

from engine.profiles import PREF_HELP, custom_profile, get_profile, merge_profiles
from tests.conftest import P


def test_custom_profile_is_deterministic_and_order_independent():
    assert custom_profile("nostairs,kerb") == custom_profile("kerb, nostairs")


def test_custom_profile_values():
    k = custom_profile("nostairs,incline:6,width:0.9,bench:300,speed:3")
    p = get_profile(k)
    assert p["hard"]["forbid_steps"] and p["hard"]["max_incline_pct"] == 6 and p["hard"]["min_width_m"] == 0.9
    assert p["bench_every_m"] == 300 and p["speed_kmh"] == 3


@pytest.mark.parametrize("bad", ["", "zly", "incline:99", "incline:x", "width:5", "speed:1"])
def test_invalid_preferences_rejected(bad):
    with pytest.raises(ValueError):
        custom_profile(bad)


def test_merge_takes_stricter_threshold():
    m = merge_profiles(["wozek_inwalidzki", "senior"])
    assert m["hard"]["max_incline_pct"] <= get_profile("senior")["hard"].get("max_incline_pct", 99)


def test_custom_profile_routes(net):
    k = custom_profile("nostairs")
    rs = {r["id"]: r for r in net.route_alternatives(P[1], P[7], [k])}
    assert rs["dostepna"]["hazard_counts"].get("blokada", 0) == 0


def test_every_preference_is_documented():
    assert {"nostairs", "kerb", "smooth", "tactile", "sound", "lit"} <= set(PREF_HELP)
