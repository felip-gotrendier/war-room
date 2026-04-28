# Repository-to-platform mapping

<!-- stub: validate in Phase 2 -->

This file maps GoTrendier repositories to the platforms they affect. The
`release-metric-correlation` skill uses this mapping to classify releases as
coincidental when the metric drop is platform-specific and the release is in
an unrelated repository.

This mapping is based on ADR-001 design assumptions and the release-agent
context as of Phase 1a. Validate against the actual release-agent repository
list in Phase 2.

## Tracked repositories

The following repositories are tracked by release-agent for GoTrendier
production. `trendify-test-project` is release-agent's sandbox environment
and is not a GoTrendier production service — war-room does not query it.

| Repository | Platforms affected | Integration status | Notes |
|------------|-------------------|--------------------|-------|
| `android` | mx_android, co_android | Active | Mobile Android app for both markets |
| `backend` | mx_android, mx_ios, co_android, co_ios | Pending production integration | API layer serving all mobile platforms |
| `notisfier` | mx_android, mx_ios, co_android, co_ios | Pending production integration | Push notification service; affects engagement metrics, not funnel conversion |

Note: `ios` and `web` repositories are not tracked by release-agent as of
Phase 1a. Do not include iOS or web releases in correlation findings until
confirmed tracked.

## Using this mapping

A release in `android` is coincidental for a drop observed only on `mx_ios`.
A release in `backend` is relevant for any cross-platform or mobile drop.
A release in `notisfier` is coincidental for funnel conversion drops (it
affects notification delivery, not checkout).

When the repository list from release-agent contains repositories not listed
here: treat them as unknown scope and note this explicitly in the correlation
finding. Do not assume they are coincidental — they may be newly added
services with undocumented platform impact.
