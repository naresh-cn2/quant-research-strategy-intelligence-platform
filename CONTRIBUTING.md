#!/usr/bin/env bash
# QRSIP — CONTRIBUTING.md
#
# How to contribute to QRSIP.
#
# 1. Read the architecture.
#    - README.md
#    - docs/architecture/overview.md
#    - docs/specifications/p02_master_architecture_specification.md
#    - PROJECT_STATUS.md
#    - docs/decisions/*.md
#
# 2. Read the relevant issue or create one.
#
# 3. Make the change in a feature branch.
#
# 4. Run the local CI pipeline:
#       make ci
#
# 5. Ensure tests pass:
#       make test
#
# 6. Ensure formatting and linting pass:
#       make format
#       make lint
#       make typecheck
#
# 7. Update documentation if behavior changes.
#
# 8. Keep commits intentional and reviewable.
#
# 9. Do NOT commit:
#    - .env
#    - secrets
#    - raw datasets
#    - local state
#
# 10. Open a PR against the appropriate target branch.
