"""Call real generated tools and check the requests they build.

The coverage tests read tools.py as text and the runtime tests exercise call()
directly, so without this nothing proves a generated function actually
produces the request its docstring claims.
"""

import json

import httpx
import pytest

from sonarr_mcp import runtime, tools


@pytest.fixture(autouse=True)
def transport(monkeypatch):
    monkeypatch.setenv("SONARR_API_KEY", "k")
    monkeypatch.setenv("SONARR_URL", "http://sonarr.test")
    runtime._http = None
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        seen["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={"ok": True})

    runtime._http = httpx.Client(
        base_url="http://sonarr.test",
        headers={"X-Api-Key": "k"},
        transport=httpx.MockTransport(handler),
    )
    yield seen
    runtime._http = None


def test_a_collection_read_hits_the_collection(transport):
    result = json.loads(tools.list_series())
    assert result["status"] == "success"
    assert transport["method"] == "GET"
    assert transport["path"] == "/api/v3/series"
    assert transport["query"] == {}


def test_a_path_parameter_lands_in_the_url(transport):
    tools.get_series_by_id(42)
    assert transport["path"] == "/api/v3/series/42"


def test_query_parameters_are_sent_under_their_wire_names(transport):
    tools.list_series(tvdb_id=1234)
    assert transport["query"] == {"tvdbId": "1234"}


def test_unset_query_parameters_are_omitted(transport):
    tools.list_series(tvdb_id=1234, include_season_images=None)
    assert "includeSeasonImages" not in transport["query"]


def test_a_body_is_sent_as_json(transport):
    tools.create_command({"name": "RefreshSeries"})
    assert transport["method"] == "POST"
    assert transport["path"] == "/api/v3/command"
    assert transport["body"] == {"name": "RefreshSeries"}


def test_a_delete_reaches_the_right_record(transport):
    tools.delete_series_by_id(7)
    assert transport["method"] == "DELETE"
    assert transport["path"] == "/api/v3/series/7"


def test_a_failure_comes_back_as_a_structured_error(monkeypatch):
    runtime._http = httpx.Client(
        base_url="http://sonarr.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
    )
    result = json.loads(tools.get_series_by_id(999))
    assert result["status"] == "error"
    assert "id" in result["message"]


def test_read_tools_are_marked_read_only():
    import asyncio

    registered = {t.name: t for t in asyncio.run(runtime.mcp.list_tools())}
    assert registered["list_series"].annotations.readOnlyHint is True
    assert registered["delete_series_by_id"].annotations.destructiveHint is True
    assert registered["create_command"].annotations.readOnlyHint is False
