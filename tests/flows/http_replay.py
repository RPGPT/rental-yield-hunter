"""Record / replay of real HTTP traffic for the flow tests.

The scrapers create sessions via ``curl_cffi.requests.Session(...)``. Both the recorder and the replayer patch that
attribute, so the harness keeps working whatever the internal structure of the scrapers is, as long as they keep
creating sessions through ``curl_cffi.requests.Session``.

Recordings live in ``tests/fixtures/http/*.json.gz`` as ``{"meta": {...}, "exchanges": [...]}``.
"""

from __future__ import annotations

import copy
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional
from unittest import mock

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def request_key(method: str, url: str, params: Optional[dict] = None, body=None) -> str:
    parts = [method.upper(), url]
    if params:
        parts.append(json.dumps(params, sort_keys=True, ensure_ascii=False))
    if body is not None:
        parts.append(json.dumps(body, sort_keys=True, ensure_ascii=False))
    return " ".join(parts)


# ── Response shrinking (keeps only what the scrapers read) ──────────────────

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_ERA_TOKEN_RE = re.compile(r"<input[^>]*__RequestVerificationToken[^>]*>")
_ERA_ATTR_RE = re.compile(r'data-(?:moduleid|tabid)="\d+"')


def _shrink_html(text: str) -> str:
    out = []
    m = _NEXT_DATA_RE.search(text)
    if m:
        try:
            build_id = json.loads(m.group(1)).get("buildId")
        except ValueError:
            build_id = None
        out.append(f'<script id="__NEXT_DATA__" type="application/json">{json.dumps({"buildId": build_id})}</script>')
    token = _ERA_TOKEN_RE.search(text)
    if token:
        out.append(token.group(0))
    attrs = _ERA_ATTR_RE.findall(text)
    if attrs:
        out.append(f"<div {' '.join(dict.fromkeys(attrs))}></div>")
    return "\n".join(out) if out else text


def _shrink_json(data):
    if not isinstance(data, dict):
        return data
    page_props = data.get("pageProps")
    if isinstance(page_props, dict):
        if "ad" in page_props:
            ad = page_props.get("ad") or {}
            return {"pageProps": {"ad": {k: ad.get(k) for k in ("id", "description", "fullDescription")}}}
        search_ads = (page_props.get("data") or {}).get("searchAds")
        if search_ads is not None:
            return {"pageProps": {"data": {"searchAds": search_ads}}}
    return data


def shrink(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.dumps(_shrink_json(json.loads(text)), ensure_ascii=False)
        except ValueError:
            return text
    return _shrink_html(text)


# ── Fake response ───────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


# ── Recorder ────────────────────────────────────────────────────────────────


class Recorder:
    def __init__(self):
        self.exchanges: list[dict] = []
        self._real_session_cls = None

    def _make_session_cls(self):
        recorder = self
        real_cls = self._real_session_cls

        class RecordingSession:
            def __init__(self, *args, **kwargs):
                self._s = real_cls(*args, **kwargs)

            def _record(self, method, url, params, body, resp):
                recorder.exchanges.append(
                    {
                        "method": method,
                        "url": url,
                        "params": params,
                        "json": body,
                        "status": resp.status_code,
                        "text": shrink(resp.text) if resp.status_code == 200 else "",
                    }
                )
                return resp

            def get(self, url, params=None, **kwargs):
                return self._record("GET", url, params, None, self._s.get(url, params=params, **kwargs))

            def post(self, url, json=None, params=None, **kwargs):
                return self._record("POST", url, params, json, self._s.post(url, json=json, params=params, **kwargs))

            def close(self):
                self._s.close()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.close()

        return RecordingSession

    def patch(self):
        import curl_cffi.requests

        self._real_session_cls = curl_cffi.requests.Session
        return mock.patch.object(curl_cffi.requests, "Session", self._make_session_cls())

    def save(self, path: Path, meta: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump({"meta": meta, "exchanges": self.exchanges}, fh, ensure_ascii=False)


# ── Replayer ────────────────────────────────────────────────────────────────


class UnrecordedRequest(AssertionError):
    pass


Transform = Callable[[str, dict, object], object]


class Replayer:
    """Serves recorded responses. Unknown requests raise ``UnrecordedRequest``.

    ``transform(url, exchange, parsed_json) -> parsed_json`` can mutate JSON bodies (e.g. drop a listing or change a
    price) to simulate a later scrape on top of real data.
    """

    def __init__(self, recording: dict, transform: Optional[Transform] = None):
        self.meta = recording["meta"]
        self._responses: dict[str, list[dict]] = defaultdict(list)
        for ex in recording["exchanges"]:
            self._responses[request_key(ex["method"], ex["url"], ex.get("params"), ex.get("json"))].append(ex)
        self._cursor: dict[str, int] = defaultdict(int)
        self.transform = transform
        self.requests: list[str] = []
        self.unrecorded: list[str] = []

    def respond(self, method, url, params=None, body=None) -> FakeResponse:
        key = request_key(method, url, params, body)
        self.requests.append(key)
        candidates = self._responses.get(key)
        if not candidates:
            self.unrecorded.append(key)
            raise UnrecordedRequest(key)
        idx = min(self._cursor[key], len(candidates) - 1)
        self._cursor[key] += 1
        ex = candidates[idx]
        text = ex["text"]
        if self.transform and ex["status"] == 200 and text[:1] in "{[":
            data = self.transform(url, ex, copy.deepcopy(json.loads(text)))
            text = json.dumps(data, ensure_ascii=False)
        return FakeResponse(ex["status"], text)

    def _make_session_cls(self):
        replayer = self

        class ReplaySession:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, url, params=None, **kwargs):
                return replayer.respond("GET", url, params)

            def post(self, url, json=None, params=None, **kwargs):
                return replayer.respond("POST", url, params, json)

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

        return ReplaySession

    def patch(self):
        import curl_cffi.requests

        return mock.patch.object(curl_cffi.requests, "Session", self._make_session_cls())


def load_recording(name: str = "recording") -> dict:
    with gzip.open(FIXTURES_DIR / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)
