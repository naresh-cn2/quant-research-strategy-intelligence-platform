# QRSIP — data
#
# This directory holds data artifacts and documentation for the data strategy.
#
# ## Directories
#
# - raw/     — raw data (never commit to the repository)
# - staged/  — staged data awaiting validation
# - curated/ — validated, curated datasets
# - artifacts/ — experiment artifacts
#
# ## Data policy
#
# - Raw datasets are not committed.
# - Data contracts are validated before use (spec §21).
# - Dataset manifests include checksums and version information.
# - Point-in-time access is enforced to prevent look-ahead (spec §17).
#
# See docs/data_strategy.md when it exists.
#
# ## External data
#
# P02 consumes P01 through a contract. Where P01 is unavailable, deterministic
# fixtures are used for development and are clearly labeled as fixtures.
