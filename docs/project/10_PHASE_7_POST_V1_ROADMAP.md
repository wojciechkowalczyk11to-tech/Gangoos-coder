# Phase 7 — Post-v1 Roadmap

## Status

Phase 7 is intentionally outside the `v1.0.0` critical path.

This phase collects work that is valuable but must not block the first stable release.
The purpose is to preserve ambition without corrupting release discipline.

---

## Non-blocking Focus Areas

### R1. Mojo dataset pipeline for future CodeAct improvement
Potential work:
- curated task corpus
- execution traces
- failure labels
- benchmark suites
- replay harnesses

Not a blocker for v1 because:
- baseline contract truth and runtime support matter first

### R2. Qwen fine-tuning pipeline
Potential work:
- dataset preparation
- eval benchmark
- fine-tune experiments
- rollback/compare strategy
- cost/performance matrix

Not a blocker for v1 because:
- a stable supported runtime matters before model optimization

### R3. Expanded multi-model orchestration
Potential work:
- smarter routing
- policy-based provider selection
- confidence-aware fallback
- cost-aware scheduling
- model capability registry

Not a blocker for v1 because:
- the first release needs truthful contracts, not maximal sophistication

### R4. Additional interfaces and UX
Potential work:
- richer CLI flows
- web UI refinement
- status dashboards
- operator tooling
- better trace visualizations

Not a blocker for v1 because:
- release credibility depends on baseline correctness first

### R5. Extended observability
Potential work:
- richer metrics
- traces
- dashboards
- alerting
- operator SLOs

Not a blocker for v1 because:
- basic health and bounded smoke coverage are sufficient for first release

---

## Roadmap Rules

1. No Phase 7 item may block `v1.0.0`.
2. Every Phase 7 item must become its own tracked milestone or PR series.
3. Ambitious work must start from the stabilized org baseline, not the pre-release repo.
4. Fine-tune work must define evaluation before or alongside training.
5. Dataset work must define provenance, quality rules, and privacy/safety boundaries.
6. No Phase 7 milestone may quietly change the Phase 1-6 guarantees.

---

## Suggested Milestone Order

### M1. Evaluation baseline before fine-tuning
Define what “better” means before training anything.

### M2. Dataset pipeline
Build curation, validation, and benchmark infrastructure.

### M3. Remote runtime hardening beyond v1
Improve throughput, caching, concurrency, and observability.

### M4. Smarter orchestration
Add policy/routing sophistication after truth and reliability are stable.

### M5. UX/operator tooling
Improve ergonomics once runtime and governance are solid.

---

## Suggested PR Structure

- one milestone at a time
- one responsibility per PR
- keep six-test discipline
- preserve release gates from Phases 1-6
- no “big bang” post-v1 rewrite

---

## Suggested Work Tracking

For each post-v1 milestone create:
- one milestone doc
- one acceptance-criteria doc
- one test/eval doc
- one implementation PR series

---

## Definition of Done

Phase 7 is not “done” as one event.
It is a controlled backlog of non-blocking growth work that starts only after the stable baseline exists.
