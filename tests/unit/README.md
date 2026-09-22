# QRSIP — Unit tests
#
# Unit tests verify individual module behavior in isolation.
#
# Scope:
# - config
# - errors
# - logging
# - doctor
# - CLI parsing (where applicable)
#
# These tests must not depend on databases, external services,
# or non-trivial filesystem state unless that state is explicitly
# part of the unit under test.
