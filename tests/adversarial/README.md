# QRSIP — Adversarial tests
#
# Adversarial tests deliberately attempt to break the system.
#
# They are NOT "does it crash" tests. Each adversarial test must have:
# - an explicit expected failure mode
# - evidence that the failure mode is correct
#
# Examples:
# - future data injection
# - timestamp manipulation
# - duplicate timestamps
# - malformed schemas
# - invalid OHLC
# - negative/zero volume
# - empty/single-row datasets
# - NaN/Inf propagation
# - negative cash
# - huge positions
# - invalid configuration
# - corrupted seeds/artifacts
#
# See spec §30.
