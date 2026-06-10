"""
Tests for the Plotly.js download robustness in ``scripts/deep_dive.py``.

Covers the fallback behavior added 2026-06-04 after an internet outage
killed an overnight dive: ``_download_plotly_with_retry`` must return
None (not raise) on persistent network failure, and ``_plotly_script_tag``
must then fall back to the plain CDN ``<script src>`` reference so the
dive still ships.

The script is imported via ``importlib`` because it lives in ``scripts/``
rather than the gopvpsim package (same pattern as test_iv_categories.py).
"""
from __future__ import annotations

import importlib.util
import socket
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"

_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)


_FAILURES = [
    pytest.param(urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")),
                 id="dns-failure"),
    pytest.param(socket.timeout("timed out"), id="socket-timeout"),
    pytest.param(ConnectionResetError("connection reset"), id="connection-reset"),
]


@pytest.fixture
def no_backoff_sleep(monkeypatch):
    """Zero out the retry backoff so tests don't sleep 21s."""
    monkeypatch.setattr(deep_dive, 'PLOTLY_DOWNLOAD_BACKOFF', (0, 0, 0))


@pytest.fixture
def captured_warnings(monkeypatch):
    """Capture deep_dive.logger.warning messages (handler setup may not
    propagate to root, so caplog isn't reliable here)."""
    messages = []
    monkeypatch.setattr(deep_dive.logger, 'warning',
                        lambda msg, *a, **k: messages.append(str(msg)))
    return messages


@pytest.mark.parametrize("exc", _FAILURES)
def test_download_retries_then_returns_none(exc, monkeypatch, no_backoff_sleep,
                                            captured_warnings):
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append(args)
        raise exc

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    result = deep_dive._download_plotly_with_retry()

    assert result is None
    assert len(calls) == 3, "should retry exactly len(BACKOFF) times"
    assert any('fall back to the CDN' in m for m in captured_warnings), (
        f"expected persistent-failure warning, got: {captured_warnings}")


def test_standalone_tag_falls_back_to_cdn_reference(monkeypatch, no_backoff_sleep,
                                                    captured_warnings):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError(socket.gaierror(8, "nodename nor servname"))

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    tag = deep_dive._plotly_script_tag(standalone=True)

    assert tag == f'<script src="{deep_dive.PLOTLY_CDN}"></script>'
    assert any('fall back to the CDN' in m for m in captured_warnings)


def test_shared_dir_tag_falls_back_to_cdn_reference(tmp_path, monkeypatch,
                                                    no_backoff_sleep,
                                                    captured_warnings):
    def fake_urlopen(*args, **kwargs):
        raise socket.timeout("timed out")

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    shared = tmp_path / "plotly_shared"
    tag = deep_dive._plotly_script_tag(standalone=False,
                                       shared_plotly_dir=str(shared),
                                       html_path=str(tmp_path / "dive.html"))

    assert tag == f'<script src="{deep_dive.PLOTLY_CDN}"></script>'
    assert not (shared / deep_dive.PLOTLY_FILENAME).exists(), (
        "no plotly file should be written on failed download")


def test_standalone_tag_inlines_on_success(monkeypatch):
    class FakeResponse:
        def read(self):
            return b"/* plotly */"
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr('urllib.request.urlopen',
                        lambda *a, **k: FakeResponse())
    tag = deep_dive._plotly_script_tag(standalone=True)
    assert tag == '<script>/* plotly */</script>'
