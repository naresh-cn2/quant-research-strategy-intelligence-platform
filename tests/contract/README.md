# QRSIP — Contract tests
#
# Contract tests verify that QRSIP honors its external contracts.
#
# The primary external contract for P02 is the P01 data contract.
#
# Where the real P01 system is unavailable, these tests use explicitly
# labeled deterministic fixtures. They do NOT pretend the fixture is
# the actual P01 implementation (spec §A8, §P01 policy).
#
# Contract tests include:
# - P01 data schema contract
# - Point-in-time access contract
# - Dataset manifest contract
