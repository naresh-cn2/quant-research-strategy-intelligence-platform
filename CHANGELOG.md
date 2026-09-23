# QRSIP — CHANGELOG.md

Changelog for QRSIP.

Format: Keep a Changelog (https://keepachangelog.com/)

## Unreleased

### Added
- **Phase 0 (Foundation)**:
  - CLI entrypoint (`qrsip init`, `qrsip doctor`, `qrsip status`).
  - Configuration loader with environment variable overrides (`QRSIP_*`) and secret sanitization.
  - Fail-closed error hierarchy rooted in `QRSIPError` with structured context dictionaries.
  - Structured JSON logging (`StructuredFormatter`) and human console output with `timed_event`.
  - Non-destructive diagnostic health checks (`Doctor`).
  - `StoragePort` protocol and portable `FileStorage` implementation with canonical JSON serialization and SHA-256 content addressing.
  - Development toolchain configs (Ruff, strict mypy, Bandit, Pytest) and container definitions (`Dockerfile`, `docker-compose.yml`).
- **Phase 1 (Domain Core)**:
  - Immutable Pydantic v2 `BaseEntity` with stable identity, semantic versioning, and UTC timestamps.
  - Research domain entities: `ResearchQuestion` (FR-001), `Hypothesis` (FR-002), `StrategySpec` (FR-003), `DatasetRef` (FR-004), `Experiment` and `ExperimentRun` (FR-005).
  - 12-state research lifecycle machine with `require_transition` fail-closed gate.
  - Append-only `ResearchRegistry` backed by `StoragePort` with conflict detection on identical keys.
  - Result envelopes: `ValidationResult`, `PromotionDecision` (human approval gate), and `ResearchReport`.
- **Phase 2 (Data Layer)**:
  - `P01DataContract` market data protocol and `Bar` dataclass (close-timestamped in UTC).
  - Fail-closed bar validator (`validate_bars`) for OHLC bounds, duplicate timestamps, ordering, and non-negativity.
  - `MarketDataset` and `PointInTimeView` enforcing strict causality and raising `LookAheadError` on future data inspection.
  - Deterministic test fixtures (`FixtureP01Provider`, `build_fixture_bars`).
- **Phase 3 (Quant Layer)**:
  - Causal features (SMA, EMA, simple/log returns, rolling volatility, momentum) with explicit warm-up `None` values.
  - Strategy signal protocol (`SignalStrategy`), `Signal` class, and `MovingAverageCrossStrategy`.
  - Financial performance metrics (Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Profit Factor, `PerformanceMetrics`) with fail-closed handling for undefined ratios.
- **Documentation**:
  - Full synchronization of `README.md`, `PROJECT_STATUS.md`, and architecture docs with actual current implementation state.

### Changed
- Updated `PROJECT_STATUS.md` with complete layer matrix, current test counts, and explicit inventory of in-progress simulation and validation files.
- Expanded `README.md` to comprehensively document architecture, data boundaries, point-in-time safety, execution timing, testing evidence, and development instructions.
