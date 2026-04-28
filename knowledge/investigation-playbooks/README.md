# Investigation playbooks

This directory contains anchored investigation patterns for known GoTrendier
incident types. A playbook describes the symptoms that trigger it, the sequence
of sources to query, the hypotheses to test, and the evidence that confirms or
refutes each hypothesis.

**Provenance note**: the first playbook (`metric-drop-release-correlation.md`)
is based on the ADR-001 anchor use case and design assumptions, written before
any real investigation was run. It is a starting point, not a validated pattern.
Subsequent playbooks should be derived from real Phase 2 investigations: observe
what query sequences actually produced results, what hypotheses were confirmed,
and what false positives recurred — then write the playbook from that evidence.
Do not write new playbooks from assumptions alone.

## File format

```markdown
# <Playbook name>

## Symptoms
<what the PM observes that should trigger this playbook>

## Trigger conditions
<when to use this playbook vs. a different one>

## Investigation sequence
<ordered steps: which skill, which source, which parameters>

## Hypotheses to test
<named hypotheses with their confirming and refuting evidence>

## Known false positives
<patterns that look like this incident type but are not>

## Confirming evidence
<what findings close the investigation with high confidence>
```

## Currently documented

- `metric-drop-release-correlation.md` — funnel metric drop correlated with
  a recent release (anchor use case)
