# MCP server specification: pulse

**Project**: war-room (Atlas Layer 3, GoTrendier)
**Prepared by**: war-room team
**Date**: 2026-04-27
**Status**: Specification — pending implementation by pulse team

---

## Context

war-room is GoTrendier's incident investigation tool. It is an LLM-based agent
that answers PMs' questions about metric regressions by querying connected
sources via MCP (Model Context Protocol). pulse is one of those sources.

This document specifies the MCP interface that war-room requires from pulse.
It is written for the pulse team to implement. It does not prescribe pulse's
internal architecture — only the tool signatures and response contracts that
war-room will call.

---

## Required tools

### `check_metric`

Retrieves a metric's time series for a given time window.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | yes | Metric identifier, e.g. `users_product_list/active` |
| `window` | object | yes | `{ start: ISO8601 date, end: ISO8601 date }` |
| `platform` | string | no | Platform filter, e.g. `mx_android`. If absent, returns all platforms. |

**Response** (WarRoomResponse envelope):

```json
{
  "data": {
    "metric": "users_product_list/active",
    "platform": "mx_android",
    "series": [
      { "date": "2026-04-20", "value": 42300 },
      { "date": "2026-04-21", "value": 41800 }
    ]
  },
  "coverage": {
    "requested": { "name": "users_product_list/active", "window": { "start": "2026-04-14", "end": "2026-04-27" }, "platform": "mx_android" },
    "covered":   { "name": "users_product_list/active", "window": { "start": "2026-04-14", "end": "2026-04-26" }, "platform": "mx_android" },
    "is_complete": false,
    "gaps": ["2026-04-27 data not yet computed"],
    "freshness_at": "2026-04-27T08:00:00Z"
  }
}
```

`data` and `error` are mutually exclusive. `coverage` is always present.

**Coverage semantics**:
- `is_complete: true` means `covered` equals `requested` and all data points
  are present.
- `is_complete: false` requires a non-empty `gaps` array describing what is
  missing in human-readable terms.
- `freshness_at` is the timestamp of the most recent data ingestion that
  contributed to this response.

---

### `get_recent_anomalies`

Returns metrics that pulse's automated detection has flagged as anomalous
in the requested window.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `window` | object | yes | `{ start: ISO8601 date, end: ISO8601 date }` |

**Response**:

```json
{
  "data": {
    "anomalies": [
      {
        "metric": "users_checkout/active",
        "platform": "mx_android",
        "onset_date": "2026-04-22",
        "severity": "high",
        "description": "30% drop from rolling baseline"
      }
    ]
  },
  "coverage": {
    "requested": { "window": { "start": "2026-04-14", "end": "2026-04-27" } },
    "covered":   { "window": { "start": "2026-04-14", "end": "2026-04-27" } },
    "is_complete": true,
    "gaps": [],
    "freshness_at": "2026-04-27T08:00:00Z"
  }
}
```

If no anomalies are detected: `"anomalies": []`. This is not an error.

---

### `trigger_scan`

Requests a fresh computation of a metric. Used when `check_metric` returns
stale data (freshness_at is too old relative to the requested window).

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | yes | Metric identifier |
| `window` | object | yes | `{ start: ISO8601 date, end: ISO8601 date }` |

**Response**:

```json
{
  "data": {
    "scan_id": "scan_abc123",
    "status": "queued",
    "estimated_completion": "2026-04-27T09:15:00Z"
  },
  "coverage": {
    "requested": { "name": "users_checkout/active", "window": { "start": "2026-04-14", "end": "2026-04-27" } },
    "covered":   {},
    "is_complete": false,
    "gaps": ["scan in progress — data not yet available"],
    "freshness_at": null
  }
}
```

`trigger_scan` is asynchronous. war-room does not poll for completion within
the same investigation session. It notes the scan has been triggered and
informs the PM that data will be available in a future session.

---

## Error contract

When a tool cannot return data, `data` is absent and `error` is present:

```json
{
  "error": {
    "code": "SOURCE_UNAVAILABLE",
    "retryable": true,
    "message": "pulse data pipeline is temporarily unavailable"
  },
  "coverage": {
    "requested": { "name": "users_checkout/active", "window": { "start": "2026-04-14", "end": "2026-04-27" }, "platform": "mx_android" },
    "covered":   {},
    "is_complete": false,
    "gaps": ["source unavailable"],
    "freshness_at": null
  }
}
```

Standard error codes (war-room handles all of these):

| Code | Retryable | When to use |
|------|-----------|-------------|
| `SOURCE_UNAVAILABLE` | true | Data pipeline unreachable or down |
| `AUTH_FAILURE` | false | Authentication to pulse failed |
| `INVALID_PARAMS` | false | Required parameter missing or malformed |
| `DATA_NOT_FOUND` | false | Metric name does not exist in pulse |
| `PARTIAL_FAILURE` | true | Some platforms returned data, others failed |
| `RATE_LIMITED` | true | Request rate exceeded |

For `PARTIAL_FAILURE`: return `data` with the platforms that succeeded and
`error` absent; use the `coverage` fields to describe which platforms are
missing. Do not return `error` if any platform succeeded.

---

## Platforms

The following platform identifiers are expected in war-room's queries.
Return data using these exact identifiers:

- `mx_android`
- `mx_ios`
- `co_android`
- `co_ios`

---

## Coordination notes

- war-room will retry once on `retryable: true` errors before reporting
  partial coverage to the PM. No further retries.
- war-room does not version MCP contracts. Changes to tool signatures or
  response structure require coordination with the war-room team before
  deployment. Contact: felip.costa@gotrendier.com.
- `trigger_scan` is a new capability. If it cannot be implemented by the
  time war-room reaches Phase 2, war-room can operate without it — it will
  report stale data rather than triggering a fresh scan.
