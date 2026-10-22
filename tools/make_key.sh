#!/bin/sh
# Generates a new extension key pair. Prints the public "key" for manifest.json and
# the extension ID it produces. The private key is only needed to pack a .crx, which
# this project never does, so it is written to a temp file and deleted.
set -e
tmp=$(mktemp)
openssl genrsa 2048 2>/dev/null > "$tmp"
der=$(openssl rsa -in "$tmp" -pubout -outform DER 2>/dev/null | base64 | tr -d '\n')
rm -f "$tmp"
echo "key: $der"
printf '%s' "$der" | sh "$(dirname "$0")/extension_id.sh"
