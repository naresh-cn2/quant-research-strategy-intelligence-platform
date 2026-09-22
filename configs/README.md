# QRSIP — Configuration directory
#
# This directory holds YAML configuration layers for:
#
#   environments/   — runtime environment profiles
#   datasets/       — dataset manifests and data contracts
#   strategies/     — strategy specifications
#   risk/           — risk configuration
#   execution/      — execution model configuration
#   experiments/    — experiment configurations
#
# Configuration is schema-validated before use. Malformed configuration
# fails closed (spec §4.8, §28).
#
# Secrets are NEVER stored here. See .env.example and SECURITY.md.
