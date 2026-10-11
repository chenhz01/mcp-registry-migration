# Changelog

All notable changes to this project are documented here.

## v0.1.1 — 2026-10-11 (round 2: audit + revision)

### Changed
- **Completeness (+25%)**: FAQ 4 → 5 entries; new entry explains how to bind
  the file-based query contract to HTTP without changing its semantics.
- **Correctness**: `validate` now detects duplicate server names (previously
  silently accepted); query results explicitly sorted for determinism.
- **Clarity**: intro paragraph tightened 49 → 42 words (rule 16); second-order
  effects rewritten around "archived entries become invisible after migration"
  — the actual governance risk; Limits names the rename blind spot.

### Verified
- self_test.py re-run after revision: all three tiers PASS
  (functional 4 / error-path 4 / edge 5 = 13 tests).

## v0.1.0 — 2026-10-11 (initial draft)

### Added
- `registry_compat.py`: registry record schema + canonical query interface
  (name/transport/status), `validate` (schema), `manifest-map` (legacy
  manifest -> records with per-entry warnings), `diff` (three-way migration
  report).
- `self_test.py`: functional / error-path / edge three-tier suite.
- README, MIT LICENSE, ALIGNMENT.md (16-item audit).
