# release-agent

**What it knows**: Release history for all GoTrendier repositories: deploy
timestamps, release identifiers, and narrative summaries of what each release
changed. Covers android, ios, backend, and notisfier repositories. Operates
in on-demand mode — retrieves releases for a requested time window or a
specific release ID.

**What it does NOT know**: It does not know the metric impact of a release —
it describes what changed in code, not what happened to user behavior afterward.
It does not provide file-level diffs or line-by-line change analysis. It does
not know about infrastructure changes deployed outside the tracked repositories
(manual deploys, config changes). Do not query release-agent to answer questions
about metric behavior or user impact.

**Available tools**:
- `get_releases(repo, date_range)`: call to retrieve all releases for a
  repository in a time window; use when looking for releases that temporally
  overlap with a known metric deviation.
- `get_release(repo, id)`: call to retrieve metadata for a specific release
  by ID; use when a release ID is already known and only its timestamp or
  basic metadata is needed.
- `explain_release(repo, id)`: call to retrieve a narrative of what a specific
  release changed; use for every strong and weak candidate identified by
  temporal correlation — do not assess platform impact from the release ID alone.
