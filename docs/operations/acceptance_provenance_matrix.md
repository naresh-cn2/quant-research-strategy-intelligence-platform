# QRSIP — Acceptance Specification Provenance Matrix

This document records requirement provenance for final acceptance. It does not reconstruct missing specification text. The checked-in `docs/specifications/p02_master_architecture_specification.md` is a 28-line preamble and does not contain the referenced sections §33, §35, §41, §48, §50, or §54.

## Section-reference reconstruction

| Section | Requirement recovered from repository evidence | Source | Classification |
|---|---|---|---|
| §33 | Container/fresh-environment verification is supported, but Docker is not the only supported way to run the project. | `Dockerfile:4-12`; ADR-0010 in `docs/decisions/adr_0003_0010.md:142-157` | B — DERIVED |
| §35 | Completion claims require evidence; the operational status must not claim completion without verification. | `PROJECT_STATUS.md:1-15`; derived acceptance checklist at `PROJECT_STATUS.md:109-125` | B — DERIVED |
| §41 | System health checks and acceptance tests are required; `qrsip doctor` is an L0 health-check contract. | `src/qrsip/doctor.py:1`; `tests/unit/test_doctor.py`; `tests/acceptance/README.md:1-13` | B — DERIVED |
| §48 | A fresh-environment acceptance path is required. | `scripts/bootstrap/dev_bootstrap.sh:9-12`; `tests/acceptance/README.md:6-13`; ADR-0010 | B — DERIVED |
| §50 | The repository's derived “working” checklist includes implementation, contracts, tests, CI green, documentation, and fresh-environment acceptance. | `docs/architecture/overview.md:35-50`; the overview explicitly says it is derived from the master specification | B — DERIVED |
| §54 | The specification is frozen after repository initialization and architecture changes require an ADR. | `docs/specifications/p02_master_architecture_specification.md:19-20`; ADRs document accepted architecture decisions | B — DERIVED |

The original section text for these references cannot be recovered from the available repository evidence. In particular, §50 historical content cannot be recovered from available repository evidence.

## Requirement acceptance matrix

| Requirement | Authoritative source | Verification method | Current status | Missing evidence | Internally enforceable? | External dependency? |
|---|---|---|---|---|---|---|
| P01 boundary and point-in-time data contract | `src/qrsip/data/contract.py`; `src/qrsip/data/dataset.py`; ADR-0007 | Run contract, data, and point-in-time tests | PASS | None for the generic P01 contract boundary | Yes | No |
| Deterministic fixture behavior | ADR-0007; `src/qrsip/data/fixtures.py` | Run fixture and contract tests; inspect `is_fixture` and limitations | PASS | None for fixture behavior | Yes | No |
| Generic checksum-bound Parquet loading | `src/qrsip/data/parquet.py` | Run Parquet contract tests and verify checksum/schema/row-count failure modes | PASS | None for the generic adapter contract | Yes | Only when a real artifact is supplied |
| Canonical production P01 dataset | No authoritative dataset definition or artifact found | Compare supplied artifact and manifest with the repository Parquet contract | UNRESOLVED | Dataset ID, version, provider/source, source version, schema version, instruments, frequency, timezone, coverage, row count, authoritative checksum, manifest, artifact location, and lineage | No canonical requirement is currently enforceable | Yes |
| Clean-environment acceptance | ADR-0010; `Dockerfile`; `docker-compose.yml`; `Makefile` | Run `docker compose run --rm qrsip make ci` from a clean image | BLOCKED | Supported container runtime and successful clean-container run | Yes, once a runtime is available | Yes |
| CI must be green | `docs/architecture/overview.md:48`; `docs/operations/release_checklist.md:8`; `.github/workflows/ci.yml` | Trigger CI and record successful runs for the current commit | PASS | None for verified baseline `8fc4590`; CI run `36135583631` succeeded | Yes | No |
| Security workflow | `.github/workflows/security.yml`; ADR-0009 | Execute secret scan, Bandit, dependency audit, and `pip check` in external CI | PASS | None for verified baseline `8fc4590`; Security run `36135583745` succeeded | Yes | No |
| Acceptance tests | `tests/acceptance/README.md`; `tests/acceptance/test_research_acceptance.py`; `.github/workflows/ci.yml` | Run `pytest -v -m acceptance` locally and in CI | PASS | None for the fixture-backed local acceptance path | Yes | No |
| Human promotion gate | `PromotionDecision`; CLI `promote`; acceptance/adversarial tests | Attempt approval against failed validation and record human rejection/approval behavior | PASS | None for the implemented gate behavior | Yes | No |

## P01 production-reference result

The repository does not define a canonical production P01 dataset. It defines the contract and a checksum-bound Parquet adapter, but does not provide:

- dataset ID;
- dataset version;
- provider/source;
- source version;
- schema version;
- instruments;
- frequency;
- timezone;
- coverage;
- row count;
- authoritative checksum;
- production manifest;
- artifact location;
- production lineage.

Synthetic fixtures are explicitly not production data. No production P01 requirement or artifact may be inferred from them.

## External inputs still required

1. A supported container runtime capable of building the repository Dockerfile and running the documented clean-environment command.
2. The authoritative external P01 production artifact and manifest, including the complete identity and lineage fields listed above.

No code, test, architecture, strategy, or acceptance-status changes are made by this matrix.
