# QRSIP — data strategy
#
# This document describes the data strategy for P02.
#
# ## Data lifecycle
#
# 1. Ingest (via P01 contract)
# 2. Stage
# 3. Validate (schema, duplicates, chronology, price consistency)
# 4. Quarantine failures
# 5. Curate
# 6. Version
# 7. Serve via point-in-time access
#
# ## Data contracts
#
# Each dataset has a manifest with:
# - dataset id
# - source
# - coverage period
# - instruments
# - frequency
# - timezone
# - schema version
# - checksum / content identity
#
# ## Point-in-time access
#
# Data must be accessible only as known at the simulated decision time.
# Future data access must fail explicitly (spec §17).
#
# ## Fixtures
#
# Where real P01 data is unavailable, deterministic fixtures are used for
# development. Fixtures are clearly labeled and are not represented as
# real P01 production data.
