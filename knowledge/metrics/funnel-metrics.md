# Funnel metrics

GoTrendier's purchase funnel has five stages. Each stage is tracked as active
users who reached that stage in a session.

## Stages

| Stage | Metric name pattern | Description |
|-------|--------------------|-----------------------------------------|
| 0 | `users_app_open/active` | Session started (app open or web visit) |
| 1 | `users_product_list/active` | Reached a product listing page |
| 2 | `users_product_view/active` | Opened a product detail page |
| 3 | `users_checkout/active` | Initiated checkout |
| 4 | `users_purchase/active` | Completed a purchase |

Derived rates (stage N / stage N-1) are the primary signal for detecting
where in the funnel a drop is occurring.

## Platforms

All five stages are tracked on: `mx_android`, `mx_ios`, `co_android`,
`co_ios`, `web`.

Platform naming convention in pulse queries: use the platform identifier
exactly as listed above. `mx` = Mexico, `co` = Colombia.

## Normal ranges

<!-- provisional: validate Phase 2 -->

These are design-assumption benchmarks, not validated against production data.
Replace with pulse-observed baselines once Phase 2 investigations produce
sufficient history.

| Transition | Typical conversion rate |
|------------|------------------------|
| Stage 0 → 1 | 70–85% |
| Stage 1 → 2 | 40–60% |
| Stage 2 → 3 | 15–25% |
| Stage 3 → 4 | 50–70% |

A deviation outside ±10 percentage points of the platform's own rolling
baseline (not the ranges above) should be treated as meaningful. Use the
platform's own baseline, not cross-platform averages.

## Known causal relationships

- **product_list drop**: often linked to search or feed algorithm changes,
  or to Android/iOS app releases that alter home screen navigation.
- **product_view drop**: often linked to product card rendering changes or
  deep-link handling regressions.
- **checkout drop**: often linked to checkout flow changes, payment provider
  issues, or backend releases affecting the cart/order APIs.
- **purchase drop**: often linked to payment processing changes, fraud filter
  tightening, or checkout completion backend issues.

These relationships are provisional and based on ADR-001 design assumptions.
Validate and extend from real Phase 2 investigations.

## Anomaly patterns

- **Simultaneous drop across all platforms**: suggests a backend release or
  a data pipeline issue rather than a mobile-specific change.
- **Single-platform drop**: suggests a mobile app release specific to that
  platform, or a country-level external event (payment provider outage, holiday).
- **Drop at one stage only (others stable)**: suggests a localized regression
  at that funnel step, not a broad traffic issue.
- **Gradual decline over multiple days**: suggests a release with a delayed
  user impact (e.g., a feature affecting returning users more than new sessions).
- **Sharp single-day drop followed by recovery**: consider data pipeline
  freshness issues before concluding a real metric event occurred.
