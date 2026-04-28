# MCP server specification: release-agent

**Project**: war-room (Atlas Layer 3, GoTrendier)
**Prepared by**: war-room team
**Date**: 2026-04-27
**Status**: Specification — pending implementation by release-agent team

---

## Context

war-room is GoTrendier's incident investigation tool. It is an LLM-based agent
that answers PMs' questions about metric regressions by querying connected
sources via MCP (Model Context Protocol). release-agent is one of those sources.

This document specifies the MCP interface that war-room requires from
release-agent. It is written for the release-agent team to implement. It
describes the on-demand query mode that war-room needs — release-agent may
already have batch or scheduled modes; this spec covers the on-demand surface
only.

---

## Context on current release-agent mode

war-room understands that release-agent currently operates in a push model
(releases are reported as they happen, not queried on demand). This spec
describes the on-demand query mode needed by war-room. The release-agent team
should determine whether to add this as a new MCP surface to the existing
system or as a separate deployment.

---

## Required tools

### `get_releases`

Returns releases for a repository within a time window.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `repo` | string | yes | Repository name, e.g. `android`, `backend` |
| `date_range` | object | yes | `{ start: ISO8601 date, end: ISO8601 date }` |

**Response** (WarRoomResponse envelope):

```json
{
  "data": {
    "repo": "android",
    "releases": [
      {
        "id": "android-v4.12.1",
        "deployed_at": "2026-04-21T14:30:00Z",
        "deployed_by": "deploy-bot",
        "environment": "production"
      },
      {
        "id": "android-v4.12.0",
        "deployed_at": "2026-04-18T10:00:00Z",
        "deployed_by": "deploy-bot",
        "environment": "production"
      }
    ]
  },
  "coverage": {
    "requested": { "repo": "android", "date_range": { "start": "2026-04-14", "end": "2026-04-28" } },
    "covered":   { "repo": "android", "date_range": { "start": "2026-04-14", "end": "2026-04-28" } },
    "is_complete": true,
    "gaps": [],
    "freshness_at": "2026-04-27T12:00:00Z"
  }
}
```

If no releases in the window: `"releases": []`. This is not an error.

---

### `get_release`

Returns metadata for a specific release by ID.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `repo` | string | yes | Repository name |
| `id` | string | yes | Release identifier as returned by `get_releases` |

**Response**:

```json
{
  "data": {
    "id": "android-v4.12.1",
    "repo": "android",
    "deployed_at": "2026-04-21T14:30:00Z",
    "deployed_by": "deploy-bot",
    "environment": "production",
    "previous_release_id": "android-v4.12.0"
  },
  "coverage": {
    "requested": { "repo": "android", "id": "android-v4.12.1" },
    "covered":   { "repo": "android", "id": "android-v4.12.1" },
    "is_complete": true,
    "gaps": [],
    "freshness_at": "2026-04-27T12:00:00Z"
  }
}
```

---

### `explain_release`

Returns a narrative summary of what a release changed. This is the primary
tool war-room uses to assess whether a release could plausibly have caused
a metric regression.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `repo` | string | yes | Repository name |
| `id` | string | yes | Release identifier |

**Response**:

```json
{
  "data": {
    "id": "android-v4.12.1",
    "repo": "android",
    "summary": "Updated product card layout on listing pages. Changed image aspect ratio from 4:3 to 1:1. Removed 'add to wishlist' quick action from card. Fixed crash on deep-link navigation to sold-out products.",
    "areas_affected": ["product_list", "product_view"],
    "pr_count": 4
  },
  "coverage": {
    "requested": { "repo": "android", "id": "android-v4.12.1" },
    "covered":   { "repo": "android", "id": "android-v4.12.1" },
    "is_complete": true,
    "gaps": [],
    "freshness_at": "2026-04-27T12:00:00Z"
  }
}
```

**`summary` field**: narrative description of what changed (language of the
deployment — typically Spanish for GoTrendier). war-room reads this field
and reasons about whether the changes described could plausibly affect a
given funnel metric. It is not parsed programmatically — write it for an
LLM reader. More detail is better than less. Include the functional areas
changed, not just file names.

**`areas_affected` field**: optional list of funnel stage names
(`product_list`, `product_view`, `checkout`, `purchase`) that the release
touched. If release-agent can populate this from PR labels or commit
conventions, it helps war-room's correlation. If not, omit it — war-room
will infer from `summary`.

---

## Error contract

When a tool cannot return data, `data` is absent and `error` is present:

```json
{
  "error": {
    "code": "SOURCE_UNAVAILABLE",
    "retryable": true,
    "message": "release-agent database is temporarily unavailable"
  },
  "coverage": {
    "requested": { "repo": "android", "date_range": { "start": "2026-04-14", "end": "2026-04-28" } },
    "covered":   {},
    "is_complete": false,
    "gaps": ["source unavailable"],
    "freshness_at": null
  }
}
```

Standard error codes:

| Code | Retryable | When to use |
|------|-----------|-------------|
| `SOURCE_UNAVAILABLE` | true | release-agent database unreachable |
| `AUTH_FAILURE` | false | Authentication failed |
| `INVALID_PARAMS` | false | Required parameter missing or malformed |
| `DATA_NOT_FOUND` | false | Release ID or repo does not exist |
| `PARTIAL_FAILURE` | true | Only some repos returned data |
| `RATE_LIMITED` | true | Request rate exceeded |

---

## Repository names

war-room queries production repositories only. Based on release-agent's
current state, the following repositories are in scope:

| Repository | Status | Notes |
|------------|--------|-------|
| `android` | Active | Confirmed tracked in production |
| `backend` | Pending production integration | To be confirmed by release-agent team |
| `notisfier` | Pending production integration | To be confirmed by release-agent team |

Repositories explicitly out of scope for war-room:
- `trendify-test-project`: release-agent sandbox environment, not a
  production service.

Repositories not currently tracked (confirm or add if applicable):
- `ios`: not listed in release-agent's tracked repositories as of Phase 1a.
  If iOS releases are added to release-agent, notify the war-room team.
- `web`: same as above.

When war-room calls `get_releases` for a repository and release-agent returns
`DATA_NOT_FOUND`, war-room will note the gap and continue with the repos that
did return data.

---

## Coordination notes

- war-room will retry once on `retryable: true` errors. No further retries.
- war-room does not version MCP contracts. Changes to tool signatures or
  response structure require coordination with the war-room team before
  deployment. Contact: felip.costa@gotrendier.com.
- The `explain_release` tool is the most critical for war-room's investigation
  quality. If release-agent can only implement two of the three tools at first,
  prioritize `get_releases` and `explain_release` over `get_release`.
- `areas_affected` in `explain_release` is optional. Do not block delivery
  on it — implement it as a second iteration if feasible.
