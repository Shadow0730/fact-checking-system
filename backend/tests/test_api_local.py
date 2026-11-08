"""End-to-end API run without a database: in-memory corpus, checks saved as JSON files."""
from fastapi.testclient import TestClient

from app.config import settings


def test_check_roundtrip_without_db(tmp_path, monkeypatch, corpus_dir):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    assert not settings.use_db
    from app.main import app

    with TestClient(app) as client:
        h = client.get("/health").json()
        assert h["db"] == "memory" and h["sources"] >= 4 and h["chunks"] > 0

        drafts = client.get("/api/demo-drafts").json()
        demo = next(d for d in drafts if d["name"].startswith("demo"))["text"]
        r = client.post("/api/checks", json={"text": demo, "title": "demo"})
        assert r.status_code == 200, r.text
        rep = r.json()
        verdicts = {c["verdict"] for c in rep["claims"]}
        assert {"fabricated", "misquote", "contradicted"} <= verdicts

        assert client.get(f"/api/checks/{rep['id']}").json()["id"] == rep["id"]
        assert client.get("/api/checks").json()[0]["id"] == rep["id"]
        assert client.get("/api/checks/not-a-uuid").status_code == 404

        mis = next(c for c in rep["claims"] if c["verdict"] == "misquote")
        fixed = client.post(f"/api/checks/{rep['id']}/claims/{mis['id']}/apply-fix").json()["text"]
        assert fixed != demo

        srcs = client.get("/api/sources").json()
        assert all(s["chunks"] > 0 for s in srcs)
        assert client.get("/api/eval/latest?dataset=dev").status_code == 200
    assert list((tmp_path / "checks").glob("*.json"))


def test_crash_still_has_cors_header(tmp_path, monkeypatch):
    """A crash must reach the browser as a JSON error, not look like 'backend not running'."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    from app.main import app
    from app.routers import checks

    async def boom(*a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(checks, "analyse", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/api/checks", json={"text": "Under Section 3 a cheque is valid."},
                        headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert r.json()["error"]["code"] == "INTERNAL" and "simulated failure" in r.json()["error"]["message"]
