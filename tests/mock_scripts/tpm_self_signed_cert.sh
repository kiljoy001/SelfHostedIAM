#!/bin/bash
# Mock certificate generation
echo "Generating mock certificates..."

mkdir -p certs
if [ -f "certs/cert.pem" ]; then
  echo "Error: Certificate already exists" >&2
  exit 2
fi

# Generate dummy certs
cat <<EOF > certs/cert.pem
-----BEGIN MOCK CERTIFICATE-----
MIIC4DCCAcgC...
-----END MOCK CERTIFICATE-----
EOF

echo "tpm-key-identifier" > certs/tpm.key

echo "Certificates created"
exit 0