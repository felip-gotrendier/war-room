# Repository-to-platform mapping

<!-- stub: validate in Phase 2 -->

This file maps GoTrendier repositories to the platforms they affect. The
`release-metric-correlation` skill uses this mapping to classify releases as
coincidental when the metric drop is platform-specific and the release is in
an unrelated repository.

This mapping is based on ADR-001 design assumptions. Validate against actual
release-agent repository list and engineering team knowledge in Phase 2.

## Mapping

| Repository | Platforms affected | Notes |
|------------|-------------------|-------|
| `android` | mx_android, co_android | Mobile Android app for both markets |
| `ios` | mx_ios, co_ios | Mobile iOS app for both markets |
| `backend` | mx_android, mx_ios, co_android, co_ios, web | API layer serving all platforms |
| `notisfier` | mx_android, mx_ios, co_android, co_ios | Push notification service; affects engagement metrics, not funnel conversion |
| `web` | web | Web storefront |

## Using this mapping

A release in `android` is coincidental for a drop observed only on `mx_ios`
or `web`. A release in `backend` is relevant for any platform-specific or
cross-platform drop. A release in `notisfier` is coincidental for funnel
conversion drops (it affects notification delivery, not checkout).

When the repository list from release-agent contains repositories not listed
here: treat them as unknown scope and note this explicitly in the correlation
finding. Do not assume they are coincidental — they may be newly added
services with undocumented platform impact.
