#!/bin/sh
# Reads a base64 manifest "key" on stdin and prints the Chrome extension ID it gives:
# the first 32 hex digits of sha256(DER public key), with 0-f mapped to a-p.
base64 -d | openssl dgst -sha256 -binary | od -An -tx1 | tr -d ' \n' | cut -c1-32 | tr '0-9a-f' 'a-p'
