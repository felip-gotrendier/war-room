# bi-tool

**Status**: MCP server in development — invocation deferred until contract is
published. Do not attempt to route queries to bi-tool in the current phase.

**What it will know**: Ad-hoc database queries beyond pulse's predefined
funnels. Covers non-standard metrics, custom dimensions, arbitrary time windows
not aligned with pulse's scanning cadence, and any metric not in the five
canonical funnel stages.

**Relationship to pulse**: bi-tool complements pulse rather than replacing it.
Pulse provides depth on canonical funnel metrics (rolling baselines, anomaly
detection, time-series history). Bi-tool provides breadth for one-off queries
outside those funnels.

**When to route to bi-tool (future)**:
- PM asks about a metric not in `knowledge/metrics/funnel-metrics.md`
- PM asks for a breakdown not available in pulse (e.g. by device model, city,
  cohort)
- PM asks a question that requires joining funnel data with non-funnel data

**Current routing rule**: if a PM question requires bi-tool and bi-tool is not
yet available, respond honestly: "This question requires ad-hoc data access
that is not yet connected. I can investigate using pulse's funnel metrics and
release history from release-agent — let me know if that partial answer is
useful."
