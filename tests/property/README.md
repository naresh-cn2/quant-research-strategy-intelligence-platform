# QRSIP — Property and invariant tests
#
# Property tests verify that the system satisfies invariants across a
# range of inputs, not just one hand-picked example.
#
# Examples:
# - cash + market_value = equity
# - a fill cannot exist without an order
# - a signal cannot be generated from future data
# - portfolio invariants under extreme inputs
#
# These tests are the backbone of the quantitative safety argument.
# See spec §25.
