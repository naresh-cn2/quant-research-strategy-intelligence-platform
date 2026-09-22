# QRSIP — tests/README.md
#
# The QRSIP test suite is organized by testing concern, mirroring the
# seven-layer architecture and the acceptance philosophy in the P02 spec.
#
#     tests/
#     ├── unit/          — independent module tests (L1-L4 primarily)
#     ├── integration/   — cross-module integration tests
#     ├── contract/      — P01 contract tests and fixture-based contract tests
#     ├── property/      — invariant and property-based tests
#     ├── regression/    — regression tests for fixed defects
#     ├── adversarial/   — deliberate attack tests
#     └── acceptance/    — end-to-end acceptance tests
#
# Running the suite:
#
#     make test          # full pytest suite
#     pytest -m unit     # unit tests only
#     pytest -m adversarial   # adversarial tests
#     pytest -m acceptance    # acceptance tests
#
# Quality standard:
#
# A test that only verifies an import is not acceptable. Every test must
# exercise real behavior. See spec §29, §30, §30.
#
# Deterministic tests:
#
# - Use fixed seeds where randomness is involved.
# - Use fixture data for contract tests.
# - Do not depend on wall-clock timing unless the test is about timing.
