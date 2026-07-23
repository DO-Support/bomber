#!/usr/bin/env bash
# Generate a self-signed TLS cert for nginx. Traffic rides the VPN, so a
# self-signed cert is acceptable; set CN/SAN to the hostname users will type.
#
#   ./scripts/gen_selfsigned_cert.sh jmv.internal.lan
#
# Outputs ./certs/fullchain.pem and ./certs/privkey.pem (mounted by compose).
set -euo pipefail

HOST="${1:-jmv.internal.lan}"
DAYS="${2:-825}"          # <= 825d keeps modern clients happy
OUT_DIR="./certs"

mkdir -p "$OUT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$OUT_DIR/privkey.pem" \
  -out    "$OUT_DIR/fullchain.pem" \
  -days   "$DAYS" \
  -subj   "/CN=$HOST/O=Internal/C=ZA" \
  -addext "subjectAltName=DNS:$HOST,DNS:localhost,IP:127.0.0.1"

chmod 600 "$OUT_DIR/privkey.pem"
echo "Wrote $OUT_DIR/fullchain.pem and $OUT_DIR/privkey.pem for host: $HOST (valid ${DAYS}d)"
