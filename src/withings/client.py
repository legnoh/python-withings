from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

import requests


@dataclass
class OAuth2Token:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    token_type: str = "Bearer"
    userid: Optional[int] = None
    obtained_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, skew_seconds: int = 60) -> bool:
        expiry = self.obtained_at + timedelta(seconds=self.expires_in)
        return datetime.now(timezone.utc) + timedelta(seconds=skew_seconds) >= expiry


class WithingsApiError(RuntimeError):
    def __init__(self, status: int, message: str, payload: Optional[Dict[str, Any]] = None):
        self.status = status
        self.payload = payload or {}
        super().__init__(f"Withings API error {status}: {message}")


class WithingsClient:
    AUTHORIZE_URL = "https://account.withings.com/oauth2_user/authorize2"
    API_BASE_URL = "https://wbsapi.withings.net"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        token: Optional[OAuth2Token] = None,
        timeout: int = 30,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout
        self.token = token

    def set_token(self, token: OAuth2Token) -> None:
        self.token = token

    def build_authorization_url(
        self,
        scopes: Iterable[str],
        state: str,
        *,
        mode: Optional[str] = None,
    ) -> str:
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": ",".join(scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        if mode is not None:
            query["mode"] = mode
        return f"{self.AUTHORIZE_URL}?{urlencode(query)}"

    def request_access_token(self, code: str) -> OAuth2Token:
        body = self._post_form(
            endpoint="/v2/oauth2",
            data={
                "action": "requesttoken",
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            auth_required=False,
        )
        token = self._token_from_body(body)
        self.token = token
        return token

    def refresh_access_token(self, refresh_token: Optional[str] = None) -> OAuth2Token:
        rt = refresh_token or (self.token.refresh_token if self.token else None)
        if not rt:
            raise ValueError("refresh_token is required")

        body = self._post_form(
            endpoint="/v2/oauth2",
            data={
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": rt,
            },
            auth_required=False,
        )
        token = self._token_from_body(body)
        self.token = token
        return token

    def call(
        self,
        endpoint: str,
        action: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        auth_required: bool = True,
    ) -> Dict[str, Any]:
        payload = {"action": action, **(params or {})}
        return self._post_form(endpoint=endpoint, data=payload, auth_required=auth_required)

    def get_user_devices(self) -> Dict[str, Any]:
        return self.call("/v2/user", "getdevice")

    def get_user_goals(self) -> Dict[str, Any]:
        return self.call("/v2/user", "getgoals")

    def link_devices(self, mac_addresses: list[str]) -> Dict[str, Any]:
        return self.call("/v2/user", "link", params={"mac_addresses": mac_addresses})

    def unlink_device(self, mac_address: str) -> Dict[str, Any]:
        return self.call("/v2/user", "unlink", params={"mac_address": mac_address})

    def get_measures(
        self,
        *,
        meastype: Optional[int] = None,
        meastypes: Optional[list[int]] = None,
        category: Optional[int] = None,
        startdate: Optional[datetime] = None,
        enddate: Optional[datetime] = None,
        lastupdate: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {
            "meastype": meastype,
            "meastypes": meastypes,
            "category": category,
            "startdate": _normalize_timestamp("startdate", startdate),
            "enddate": _normalize_timestamp("enddate", enddate),
            "lastupdate": lastupdate,
            "offset": offset,
        }
        return self.call("/measure", "getmeas", params=_compact(params))

    def get_activity(
        self,
        *,
        startdateymd: Optional[date] = None,
        enddateymd: Optional[date] = None,
        lastupdate: Optional[int] = None,
        offset: Optional[int] = None,
        data_fields: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdateymd": _normalize_ymd_date("startdateymd", startdateymd),
                "enddateymd": _normalize_ymd_date("enddateymd", enddateymd),
                "lastupdate": lastupdate,
                "offset": offset,
                "data_fields": data_fields,
            }
        )
        return self.call("/v2/measure", "getactivity", params=params)

    def get_intraday_activity(
        self,
        *,
        startdate: Optional[datetime] = None,
        enddate: Optional[datetime] = None,
        data_fields: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdate": _normalize_timestamp("startdate", startdate),
                "enddate": _normalize_timestamp("enddate", enddate),
                "data_fields": data_fields,
            }
        )
        return self.call("/v2/measure", "getintradayactivity", params=params)

    def get_workouts(
        self,
        *,
        startdateymd: Optional[date] = None,
        enddateymd: Optional[date] = None,
        lastupdate: Optional[int] = None,
        offset: Optional[int] = None,
        data_fields: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdateymd": _normalize_ymd_date("startdateymd", startdateymd),
                "enddateymd": _normalize_ymd_date("enddateymd", enddateymd),
                "lastupdate": lastupdate,
                "offset": offset,
                "data_fields": data_fields,
            }
        )
        return self.call("/v2/measure", "getworkouts", params=params)

    def get_sleep(
        self,
        *,
        startdate: datetime,
        enddate: datetime,
        data_fields: Optional[list[str]] = None,
        meastypes: Optional[list[int]] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdate": _normalize_timestamp("startdate", startdate),
                "enddate": _normalize_timestamp("enddate", enddate),
                "data_fields": data_fields,
                "meastypes": meastypes,
            }
        )
        return self.call("/v2/sleep", "get", params=params)

    def get_sleep_summary(
        self,
        *,
        startdateymd: Optional[date] = None,
        enddateymd: Optional[date] = None,
        lastupdate: Optional[int] = None,
        data_fields: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdateymd": _normalize_ymd_date("startdateymd", startdateymd),
                "enddateymd": _normalize_ymd_date("enddateymd", enddateymd),
                "lastupdate": lastupdate,
                "data_fields": data_fields,
            }
        )
        return self.call("/v2/sleep", "getsummary", params=params)

    def list_heart_records(
        self,
        *,
        startdate: Optional[datetime] = None,
        enddate: Optional[datetime] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "startdate": _normalize_timestamp("startdate", startdate),
                "enddate": _normalize_timestamp("enddate", enddate),
                "offset": offset,
            }
        )
        return self.call("/v2/heart", "list", params=params)

    def get_heart_signal(self, signalid: int, *, with_filtered: bool = False, with_intervals: bool = False) -> Dict[str, Any]:
        params = {
            "signalid": signalid,
            "with_filtered": str(with_filtered).lower(),
            "with_intervals": str(with_intervals).lower(),
        }
        return self.call("/v2/heart", "get", params=params)

    def notify_subscribe(self, callbackurl: str, appli: int, *, comment: Optional[str] = None) -> Dict[str, Any]:
        params = _compact({"callbackurl": callbackurl, "appli": appli, "comment": comment})
        return self.call("/notify", "subscribe", params=params)

    def notify_list(self, appli: Optional[int] = None) -> Dict[str, Any]:
        return self.call("/notify", "list", params=_compact({"appli": appli}))

    def notify_get(self, callbackurl: str, *, appli: Optional[int] = None) -> Dict[str, Any]:
        return self.call("/notify", "get", params=_compact({"callbackurl": callbackurl, "appli": appli}))

    def notify_update(
        self,
        callbackurl: str,
        appli: int,
        *,
        new_callbackurl: Optional[str] = None,
        new_appli: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = _compact(
            {
                "callbackurl": callbackurl,
                "appli": appli,
                "new_callbackurl": new_callbackurl,
                "new_appli": new_appli,
                "comment": comment,
            }
        )
        return self.call("/notify", "update", params=params)

    def notify_revoke(self, callbackurl: str, *, appli: Optional[int] = None) -> Dict[str, Any]:
        return self.call("/notify", "revoke", params=_compact({"callbackurl": callbackurl, "appli": appli}))

    def _post_form(self, endpoint: str, data: Dict[str, Any], auth_required: bool) -> Dict[str, Any]:
        normalized = _normalize_params(data)
        headers: Dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}

        if auth_required:
            if not self.token:
                raise ValueError("A token is required for this API call")
            if self.token.is_expired() and self.token.refresh_token:
                self.refresh_access_token(self.token.refresh_token)
            headers["Authorization"] = f"Bearer {self.token.access_token}"

        response = requests.post(
            f"{self.API_BASE_URL}{endpoint}",
            data=normalized,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        status = payload.get("status")
        if status != 0:
            error_message = payload.get("error") or payload.get("message") or "unknown error"
            raise WithingsApiError(status=status, message=error_message, payload=payload)

        return payload.get("body", {})

    @staticmethod
    def _token_from_body(body: Dict[str, Any]) -> OAuth2Token:
        return OAuth2Token(
            userid=body.get("userid"),
            access_token=body["access_token"],
            refresh_token=body["refresh_token"],
            expires_in=int(body["expires_in"]),
            scope=body.get("scope", ""),
            token_type=body.get("token_type", "Bearer"),
            obtained_at=datetime.now(timezone.utc),
        )


def _compact(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, list):
            normalized[key] = ",".join(_normalize_scalar(item) for item in value)
        else:
            normalized[key] = _normalize_scalar(value)
    return normalized


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalize_ymd_date(name: str, value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{name} must be a datetime.date instance")
    return value.isoformat()


def _normalize_timestamp(name: str, value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.datetime instance")
    return int(value.timestamp())
