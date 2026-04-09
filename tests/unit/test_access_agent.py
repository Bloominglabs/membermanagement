from __future__ import annotations

import importlib
import json


def test_fetch_snapshot_sends_access_agent_key_header(monkeypatch):
    module = importlib.import_module("onprem.access_agent.main")
    monkeypatch.setattr(module, "ALLOWLIST_URL", "https://example.org/api/access/allowlist/")
    monkeypatch.setattr(module, "ACCESS_AGENT_API_KEY", "agent-key")

    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"etag": "abc", "payload": {}}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    snapshot = module.fetch_snapshot("etag-1")

    assert snapshot["etag"] == "abc"
    assert captured["headers"]["X-access-agent-key"] == "agent-key"
    assert captured["url"].endswith("?v=etag-1")
