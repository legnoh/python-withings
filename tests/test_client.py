from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from withings.client import OAuth2Token, WithingsClient


class DummyResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def make_client(token: OAuth2Token | None = None) -> WithingsClient:
    return WithingsClient(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.com/callback",
        token=token,
    )


def test_build_authorization_url_contains_expected_query() -> None:
    client = make_client()

    authorization_url = client.build_authorization_url(
        scopes=["user.info", "user.metrics"],
        state="csrf-token",
    )

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "account.withings.com"
    assert parsed.path == "/oauth2_user/authorize2"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-id"]
    assert query["scope"] == ["user.info,user.metrics"]
    assert query["redirect_uri"] == ["https://example.com/callback"]
    assert query["state"] == ["csrf-token"]


def test_request_access_token_parses_withings_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    captured: dict[str, Any] = {}

    def fake_post(url: str, data: dict[str, Any], headers: dict[str, str], timeout: int) -> DummyResponse:
        captured.update({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return DummyResponse(
            {
                "status": 0,
                "body": {
                    "userid": 42,
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "user.info,user.metrics",
                    "token_type": "Bearer",
                },
            }
        )

    monkeypatch.setattr("withings.client.requests.post", fake_post)

    token = client.request_access_token("auth-code")

    assert captured["url"] == "https://wbsapi.withings.net/v2/oauth2"
    assert captured["data"] == {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "code": "auth-code",
        "redirect_uri": "https://example.com/callback",
    }
    assert "Authorization" not in captured["headers"]
    assert token.access_token == "access-token"
    assert token.refresh_token == "refresh-token"
    assert token.userid == 42
    assert client.token == token


def test_get_activity_serializes_dates_and_uses_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = OAuth2Token(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
        scope="user.activity",
    )
    client = make_client(token=token)
    captured: dict[str, Any] = {}

    def fake_post(url: str, data: dict[str, Any], headers: dict[str, str], timeout: int) -> DummyResponse:
        captured.update({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return DummyResponse({"status": 0, "body": {"activities": []}})

    monkeypatch.setattr("withings.client.requests.post", fake_post)

    body = client.get_activity(
        startdateymd=date(2026, 3, 1),
        enddateymd=date(2026, 3, 7),
        data_fields=["steps", "distance"],
    )

    assert body == {"activities": []}
    assert captured["url"] == "https://wbsapi.withings.net/v2/measure"
    assert captured["headers"]["Authorization"] == "Bearer access-token"
    assert captured["data"] == {
        "action": "getactivity",
        "startdateymd": "2026-03-01",
        "enddateymd": "2026-03-07",
        "data_fields": "steps,distance",
    }


def test_get_activity_rejects_datetime_for_ymd_params() -> None:
    token = OAuth2Token(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
        scope="user.activity",
    )
    client = make_client(token=token)

    with pytest.raises(TypeError, match="startdateymd must be a datetime.date instance"):
        client.get_activity(
            startdateymd=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            enddateymd=date(2026, 3, 7),
        )


def test_get_sleep_serializes_datetime_to_unix_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    token = OAuth2Token(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
        scope="user.sleep.events",
    )
    client = make_client(token=token)
    captured: dict[str, Any] = {}
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)

    def fake_post(url: str, data: dict[str, Any], headers: dict[str, str], timeout: int) -> DummyResponse:
        captured.update({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return DummyResponse({"status": 0, "body": {"series": {}}})

    monkeypatch.setattr("withings.client.requests.post", fake_post)

    body = client.get_sleep(startdate=start, enddate=end)

    assert body == {"series": {}}
    assert captured["data"]["startdate"] == int(start.timestamp())
    assert captured["data"]["enddate"] == int(end.timestamp())


def test_expired_token_is_refreshed_before_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    expired_token = OAuth2Token(
        access_token="expired-access-token",
        refresh_token="refresh-token",
        expires_in=1,
        scope="user.info",
        obtained_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    client = make_client(token=expired_token)
    requests_seen: list[dict[str, Any]] = []

    def fake_post(url: str, data: dict[str, Any], headers: dict[str, str], timeout: int) -> DummyResponse:
        requests_seen.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        if data["action"] == "requesttoken":
            return DummyResponse(
                {
                    "status": 0,
                    "body": {
                        "userid": 42,
                        "access_token": "fresh-access-token",
                        "refresh_token": "fresh-refresh-token",
                        "expires_in": 3600,
                        "scope": "user.info",
                        "token_type": "Bearer",
                    },
                }
            )
        return DummyResponse({"status": 0, "body": {"devices": []}})

    monkeypatch.setattr("withings.client.requests.post", fake_post)

    body = client.get_user_devices()

    assert body == {"devices": []}
    assert len(requests_seen) == 2
    assert requests_seen[0]["data"]["action"] == "requesttoken"
    assert requests_seen[1]["data"]["action"] == "getdevice"
    assert requests_seen[1]["headers"]["Authorization"] == "Bearer fresh-access-token"