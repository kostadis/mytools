from __future__ import annotations

import importlib.util
import http.client
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from read_decisions import DecisionError, normalize  # noqa: E402
from serve_review import MAX_BODY, ReviewConfig, make_server  # noqa: E402


SPEC = {
    "title": "Phone review",
    "reviewId": "phone-review:1",
    "outputName": "decisions.json",
    "items": [
        {"id": "one", "t": "One", "y": "Yes", "n": "No"},
        {"id": "two", "t": "Two", "y": "Yes", "n": "No"},
    ],
}


def payload(**changes):
    value = {
        "schemaVersion": 1,
        "reviewId": "phone-review:1",
        "savedAt": "2026-10-07 12:00 UTC",
        "decisions": {"one": "approve"},
        "notes": {},
        "unmarked": ["two"],
    }
    value.update(changes)
    return value


def request(url: str, *, data: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url, data=body, method="PUT" if body is not None else "GET",
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req) as response:
        return response.status, response.headers, response.read()


@pytest.fixture
def running_server(tmp_path):
    page = tmp_path / "review.html"
    page.write_text(
        "<!doctype html><html><head><meta charset=utf-8></head>"
        "<body><h1>Review</h1></body></html>",
        encoding="utf-8",
    )
    items = tmp_path / "review_items.json"
    items.write_text(json.dumps(SPEC), encoding="utf-8")
    output = tmp_path / "decisions.json"
    config = ReviewConfig(page, items, output, "fixed-capability", SPEC)
    server = make_server(config, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, config
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_capability_url_serves_only_the_configured_page(running_server):
    server, config = running_server
    root = f"http://127.0.0.1:{server.server_port}"
    status, headers, body = request(root + config.base_path)
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert "charset=utf-8" in headers["Content-Type"]
    assert b"<h1>Review</h1>" in body
    assert b'<meta name="codex-review-save" content="enabled">' in body
    assert b'codex-review-save' not in config.page.read_bytes()
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(root + "/")
    assert exc.value.code == 404


def test_valid_save_is_normalized_and_written_on_the_vm(running_server):
    server, config = running_server
    url = f"http://127.0.0.1:{server.server_port}{config.base_path}decisions"
    status, _headers, body = request(url, data=payload())
    assert status == 200
    assert json.loads(body)["saved"] == str(config.output)
    saved = json.loads(config.output.read_text(encoding="utf-8"))
    assert saved["decided"] == 1
    assert saved["tally"] == {"approve": 1, "discuss": 0, "reject": 0}
    assert not list(config.output.parent.glob(".decisions.json.*"))


def test_wrong_review_is_rejected_without_changing_destination(running_server):
    server, config = running_server
    config.output.write_text("keep me\n", encoding="utf-8")
    url = f"http://127.0.0.1:{server.server_port}{config.base_path}decisions"
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(url, data=payload(reviewId="some-other-review"))
    assert exc.value.code == 422
    assert config.output.read_text(encoding="utf-8") == "keep me\n"


def test_oversized_save_is_rejected_without_a_write(running_server):
    server, config = running_server
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        "PUT", config.base_path + "decisions", body=b"x",
        headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY + 1)},
    )
    response = connection.getresponse()
    assert response.status == 413
    response.read()
    connection.close()
    assert not config.output.exists()


def test_validator_rejects_stale_item_sets_and_wrong_review_ids():
    with pytest.raises(DecisionError, match="stale export"):
        normalize(payload(unmarked=[]), SPEC)
    with pytest.raises(DecisionError, match="wrong reviewId"):
        normalize(payload(reviewId="wrong"), SPEC)


@pytest.mark.parametrize("change, message", [
    ({"schemaVersion": 2}, "unsupported schemaVersion"),
    ({"savedAt": []}, "not a saved review"),
    ({"decisions": {"one": {"approve": True}}}, "unrecognised verdicts"),
    ({"unmarked": [{"id": "two"}]}, "ids must be strings"),
])
def test_validator_rejects_malformed_payloads(change, message):
    with pytest.raises(DecisionError, match=message):
        normalize(payload(**change), SPEC)


def test_generated_page_keeps_hosted_and_standalone_save_paths():
    module_spec = importlib.util.spec_from_file_location("build_review", HERE / "build_review.py")
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    html = module.build(SPEC)
    assert "Save to VM" in html
    assert "meta[name=\"codex-review-save\"]" in html
    assert "fetch(new URL('decisions'" in html
    assert "new Blob([outputText()]" in html
