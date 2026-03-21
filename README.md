# python-withings

Withings API Client for Python.

Official API reference:
https://developer.withings.com/api-reference

## Installation

```bash
uv add legnoh-withings
```

## Quick Start

### 1. Build an authorization URL

```python
from withings import WithingsClient

client = WithingsClient(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="https://example.com/callback",
)

auth_url = client.build_authorization_url(
    scopes=["user.info", "user.metrics", "user.activity", "user.sleep.events"],
    state="random-csrf-state",
)

print(auth_url)
```

### 2. Exchange authorization code for tokens

```python
token = client.request_access_token(code="AUTHORIZATION_CODE")
print(token.access_token)
```

### 3. Call APIs

```python
from datetime import date, datetime, timezone

# User-linked devices
devices = client.get_user_devices()

# Body measures
measures = client.get_measures(lastupdate=1710000000)

# Daily activity
activity = client.get_activity(
    startdateymd=date(2026, 3, 1),
    enddateymd=date(2026, 3, 7),
    data_fields=["steps", "distance", "calories"],
)

# Sleep summary
sleep_summary = client.get_sleep_summary(
    startdateymd=date(2026, 3, 1),
    enddateymd=date(2026, 3, 7),
)

# High-frequency sleep data
sleep_detail = client.get_sleep(
    startdate=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    enddate=datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc),
)
```

`startdateymd` and `enddateymd` accept `datetime.date`.
`startdate` and `enddate` accept `datetime.datetime` and are internally converted to Unix timestamps.

## Implemented Features

- OAuth2 authorization URL builder
- OAuth2 token exchange (`authorization_code`)
- OAuth2 token refresh (`refresh_token`)
- Generic API call entrypoint (`call`)
- User API (`getdevice`, `getgoals`, `link`, `unlink`)
- Measure API (`getmeas`, `getactivity`, `getintradayactivity`, `getworkouts`)
- Sleep API (`get`, `getsummary`)
- Heart API (`list`, `get`)
- Notify API (`subscribe`, `list`, `get`, `update`, `revoke`)

## Error Handling

When Withings response `status` is not `0`, the client raises `WithingsApiError`.

```python
from withings import WithingsApiError

try:
    client.get_user_devices()
except WithingsApiError as e:
    print(e.status)
    print(e)
```

## Notes

- HTTP requests to Withings are sent as `application/x-www-form-urlencoded`.
- If the token is near expiry, the client refreshes it with `refresh_token` before API calls.

## Development

### Setup

```bash
uv sync
```

### Run tests

```bash
uv run pytest
```

### Run example scripts

```bash
uv run python your_script.py
```
