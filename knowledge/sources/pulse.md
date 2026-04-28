# pulse

**What it knows**: Funnel metric time series for all GoTrendier platforms
(mx_android, mx_ios, co_android, co_ios, web). Tracks active users at each
funnel stage (product_list, product_view, checkout, purchase) and derived
rates. Provides automated anomaly detection over recent windows.

**What it does NOT know**: It does not know what caused a metric deviation —
it reports measurements only. It does not know what code was deployed or when.
It does not cover infrastructure metrics (latency, error rates, server load) —
those are in Datadog. Do not query pulse to answer questions about releases,
deployments, or code changes.

**Available tools**:
- `check_metric(name, window)`: call to retrieve a metric's time series and
  assess whether a deviation exists in the requested window; use when the PM
  names a specific metric or funnel stage.
- `get_recent_anomalies(window)`: call to discover which metrics pulse's
  automated detection has already flagged; use at investigation start when the
  PM describes a symptom without naming a specific metric.
- `trigger_scan(name, window)`: call to request a fresh computation of a metric
  when `check_metric` returns stale data (freshness_at is too old relative to
  the requested window); use sparingly — scans have compute cost.
