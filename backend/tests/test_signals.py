"""Zgloszenia spolecznosci: opis, zdjecie (bez EXIF), glosy +/-, komentarze, moderacja."""
import base64
import io

import pytest

from tests.conftest import P, make_client

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

IN = {"lon": P[1][0], "lat": P[1][1]}


def jpeg_b64(with_exif=True, size=(64, 48), fmt="JPEG") -> str:
    im = Image.new("RGB", size, (200, 80, 40))
    buf = io.BytesIO()
    kw = {}
    if with_exif and fmt == "JPEG":
        ex = Image.Exif()
        ex[0x010F] = "TajnyProducent"          # Make
        ex[0x0110] = "TajnyModelTelefonu"      # Model
        ex[0x8825] = {1: "N", 2: (50.0, 3.0, 40.0), 3: "E", 4: (19.0, 56.0, 20.0)}   # GPS
        kw["exif"] = ex
    im.save(buf, fmt, **kw)
    return base64.b64encode(buf.getvalue()).decode()


def body(**kw):
    d = dict(IN, category="zastawiony_chodnik", description="Chodnik zastawiony samochodami")
    d.update(kw)
    return d


def test_categories(client):
    r = client.get("/api/signals/categories").json()
    ids = {c["id"] for c in r["categories"]}
    assert "zastawiony_chodnik" in ids and "inne" in ids and r["limits"]["photo_format"] == "JPEG"


def test_add_list_detail(client):
    r = client.post("/api/signals", json=body())
    assert r.status_code == 201
    sig = r.json()["signal"]
    assert sig["status"] == "niezweryfikowane" and sig["up"] == 0 and sig["down"] == 0 and sig["has_photo"] is False
    lst = client.get("/api/signals").json()
    assert lst["count"] == 1 and lst["features"][0]["geometry"]["coordinates"] == [IN["lon"], IN["lat"]]
    d = client.get(f"/api/signals/{sig['id']}").json()
    assert d["description"] == "Chodnik zastawiony samochodami" and d["comments"] == [] and d["photo_url"] is None


def test_validation(client):
    assert client.post("/api/signals", json=body(category="zly")).status_code == 422
    assert client.post("/api/signals", json=body(lon=21.0, lat=52.2)).status_code == 422       # poza obszarem demo
    assert client.post("/api/signals", json=body(description="ab")).status_code == 422
    assert client.post("/api/signals", json=body(description="<b>   </b>")).status_code == 422
    assert client.get("/api/signals/zzzz").status_code == 404
    assert client.get("/api/signals/..%2f..%2fetc").status_code == 404


def test_xss_cleaned(client):
    r = client.post("/api/signals", json=body(description="<script>alert(1)</script>Dziura w chodniku", photo_alt="<img src=x onerror=1>zdjecie"))
    s = r.json()["signal"]
    assert "<" not in s["description"] and "Dziura" in s["description"]
    d = client.get(f"/api/signals/{s['id']}").json()
    assert "<" not in (d["photo_alt"] or "")


def test_photo_exif_stripped(client):
    r = client.post("/api/signals", json=body(photo=jpeg_b64(with_exif=True), photo_alt="Samochody na chodniku"))
    assert r.status_code == 201
    s = r.json()["signal"]
    assert s["has_photo"] is True
    d = client.get(f"/api/signals/{s['id']}").json()
    assert d["photo_url"] == f"/api/signals/{s['id']}/photo" and d["photo_alt"] == "Samochody na chodniku"
    ph = client.get(d["photo_url"])
    assert ph.status_code == 200 and ph.headers["content-type"] == "image/jpeg"
    assert ph.headers["x-content-type-options"] == "nosniff"
    for tajne in (b"Exif", b"TajnyProducent", b"TajnyModelTelefonu", b"GPS"):
        assert tajne not in ph.content
    im = Image.open(io.BytesIO(ph.content))
    im.load()
    assert im.size == (64, 48)


def test_photo_with_data_url_prefix(client):
    r = client.post("/api/signals", json=body(photo="data:image/jpeg;base64," + jpeg_b64()))
    assert r.status_code == 201 and r.json()["signal"]["has_photo"]


def test_bad_photos_rejected(client):
    assert client.post("/api/signals", json=body(photo=jpeg_b64(fmt="PNG"))).status_code == 422   # nie JPEG
    assert client.post("/api/signals", json=body(photo="to-nie-jest-base64!!")).status_code == 422
    assert client.post("/api/signals", json=body(photo=base64.b64encode(b"\xff\xd8\xff\xe0abc").decode())).status_code == 422
    big = base64.b64encode(b"\xff\xd8" + b"\x00" * 2_100_000).decode()
    assert client.post("/api/signals", json=body(photo=big)).status_code in (413, 422)
    assert client.get("/api/signals").json()["count"] == 0


def test_votes(net, monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "1")
    c = make_client(net)
    sid = c.post("/api/signals", json=body()).json()["signal"]["id"]
    h = lambda ip: {"x-forwarded-for": ip}
    r = c.post(f"/api/signals/{sid}/vote", json={"value": "up"}, headers=h("1.1.1.1")).json()
    assert (r["up"], r["down"], r["my_vote"]) == (1, 0, "up")
    r = c.post(f"/api/signals/{sid}/vote", json={"value": "up"}, headers=h("1.1.1.1")).json()
    assert r["up"] == 1                                                             # drugi raz to samo = bez zmiany
    r = c.post(f"/api/signals/{sid}/vote", json={"value": "down"}, headers=h("2.2.2.2")).json()
    assert (r["up"], r["down"]) == (1, 1)
    r = c.post(f"/api/signals/{sid}/vote", json={"value": "down"}, headers=h("1.1.1.1")).json()   # zmiana zdania
    assert (r["up"], r["down"], r["my_vote"]) == (0, 2, "down")
    r = c.post(f"/api/signals/{sid}/vote", json={"value": "none"}, headers=h("1.1.1.1")).json()   # cofniecie
    assert (r["up"], r["down"], r["my_vote"]) == (0, 1, None)
    assert c.post(f"/api/signals/{sid}/vote", json={"value": "super"}).status_code == 422
    assert c.post("/api/signals/abcdef12/vote", json={"value": "up"}).status_code == 404
    # glosy nie zmieniaja statusu: nadal niezweryfikowane
    assert c.get(f"/api/signals/{sid}").json()["status"] == "niezweryfikowane"


def test_questioned_flag(net, monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "1")
    c = make_client(net)
    sid = c.post("/api/signals", json=body()).json()["signal"]["id"]
    for i in range(3):
        c.post(f"/api/signals/{sid}/vote", json={"value": "down"}, headers={"x-forwarded-for": f"9.9.9.{i}"})
    assert c.get(f"/api/signals/{sid}").json()["questioned"] is True


def test_comments(client):
    sid = client.post("/api/signals", json=body()).json()["signal"]["id"]
    r = client.post(f"/api/signals/{sid}/comments", json={"text": "U mnie też tak <b>było</b>"})
    assert r.status_code == 201
    d = r.json()
    assert d["comments_count"] == 1 and d["comments"][0]["text"] == "U mnie też tak było"
    assert client.post(f"/api/signals/{sid}/comments", json={"text": "x"}).status_code == 422
    assert client.post("/api/signals/abcdef12/comments", json={"text": "komentarz"}).status_code == 404


def test_rate_limits(client):
    for _ in range(5):
        assert client.post("/api/signals", json=body()).status_code == 201
    assert client.post("/api/signals", json=body()).status_code == 429


def test_moderation(net, monkeypatch):
    c = make_client(net)
    sid = c.post("/api/signals", json=body(photo=jpeg_b64())).json()["signal"]["id"]
    cid = c.post(f"/api/signals/{sid}/comments", json={"text": "komentarz do ukrycia"}).json()["comments"][0]["id"]
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert c.get("/api/admin/signals").status_code == 404                           # bez ADMIN_TOKEN moderacja wylaczona
    monkeypatch.setenv("ADMIN_TOKEN", "sekret")
    assert c.get("/api/admin/signals").status_code == 401
    ok = {"x-admin-token": "sekret"}
    assert c.post(f"/api/admin/signals/{sid}/comments/{cid}", json={"action": "odrzucone"}, headers=ok).status_code == 200
    assert c.get(f"/api/signals/{sid}").json()["comments"] == []
    assert c.post(f"/api/admin/signals/{sid}", json={"action": "zaakceptowane"}, headers=ok).status_code == 200
    assert c.get(f"/api/signals/{sid}").json()["status"] == "sprawdzone"
    assert c.post(f"/api/admin/signals/{sid}", json={"action": "odrzucone", "note": "twarz na zdjęciu"}, headers=ok).status_code == 200
    assert c.get(f"/api/signals/{sid}").status_code == 404
    assert c.get(f"/api/signals/{sid}/photo").status_code == 404
    assert c.get("/api/signals").json()["count"] == 0
    assert any(x["id"] == sid for x in c.get("/api/admin/signals", headers=ok).json())


def test_persistence(net, tmp_path):
    from fastapi.testclient import TestClient
    from api.main import create_app
    from engine.geocode import Geocoder
    from engine.realtime import Realtime
    from engine.surveys import Surveys
    from engine.buildings import Buildings
    from engine.transit import Transit
    from pipeline.common import load_config

    def build():
        return TestClient(create_app(net=net, pois_geojson={"features": []}, facts=[], cfg=load_config(),
                                     reports_path=tmp_path / "r.json", signals_path=tmp_path / "s.json", photos_dir=tmp_path / "ph",
                                     transit=Transit(None), geocoder=Geocoder(None), realtime=Realtime(lambda n: 1 / 0),
                                     surveys=Surveys(None), buildings=Buildings(None)))
    a = build()
    sid = a.post("/api/signals", json=body(photo=jpeg_b64())).json()["signal"]["id"]
    b = build()                                            # "restart serwera"
    assert b.get(f"/api/signals/{sid}").status_code == 200 and b.get(f"/api/signals/{sid}/photo").status_code == 200
