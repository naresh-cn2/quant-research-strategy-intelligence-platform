# QRSIP — SECURITY.md
#
# Security policy for QRSIP — Quantitative Research & Strategy Intelligence Platform.
#
# Reporting vulnerabilities
# --------------------------
# If you discover a security vulnerability, please report it responsibly.
# Do NOT open a public issue for a security vulnerability.
#
# Contact:
# - Preferred: open a private security advisory via GitHub
# - Alternative: contact the repository maintainer through the repository's
#   established communication channel
#
# What to include:
# - description of the issue
# - steps to reproduce
# - potential impact
# - any known mitigations
#
# What we will do:
# - acknowledge receipt
# - investigate
# - coordinate a fix
# - publish a fix and advisory when appropriate
#
# Security boundaries
# -------------------
# - No secrets in source, config, or commits.
# - .env.example is the only committed environment example.
# - CI runs secret scanning and dependency auditing.
# - P02 must not connect to live broker accounts in the initial research release.
# - Strategy code must not bypass domain, risk, or validation contracts.
#
# Supported versions
# ------------------
# Only the current main branch is supported for security fixes.
