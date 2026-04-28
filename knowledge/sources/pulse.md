# pulse

**What it knows**: Funnel metric time series for all GoTrendier mobile
platforms (mx_android, mx_ios, co_android, co_ios). Tracks active users at
each funnel stage (product_list, product_view, checkout, purchase) and derived
rates. Provides automated anomaly detection over recent windows.

**Scope boundary**: pulse covers the five canonical funnel stages and their
derived rates. It does not cover ad-hoc metrics, custom dimensions, or queries
outside these predefined funnels. For non-funnel queries or custom breakdowns,
see bi-tool.md.

**What it does NOT know**: It does not know what caused a metric deviation —
it reports measurements only. It does not know what code was deployed or when.
It does not cover infrastructure metrics (latency, error rates, server load) —
those are in Datadog. Do not query pulse to answer questions about releases,
deployments, or code changes.

**Available tools**:
- `check_metric(metric_name, days, platform?)`: retrieve a metric's time
  series for the last N days. `metric_name` is the full metric identifier
  (e.g. `users_product_list/active`). `days` is an integer (e.g. 14).
  Optional `platform` filters to a single platform; omit for all platforms.
  Use when the PM names a specific metric or funnel stage.
- `get_recent_anomalies(days, severity?)`: discover which metrics pulse's
  automated detection has flagged in the last N days. Optional `severity`
  filter (`high`, `medium`, `low`). Use at investigation start when the PM
  describes a symptom without naming a specific metric.
- `trigger_scan()`: request a fresh computation across all active metrics.
  No parameters. Fire-and-forget — pulse responds immediately; data appears
  in `get_recent_anomalies` in ~60 seconds. Use when `get_recent_anomalies`
  returns stale data and fresh data is needed for a substantive answer.
