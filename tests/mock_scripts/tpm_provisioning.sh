#!/bin/bash
# Simulates TPM provisioning process
echo "Starting TPM provisioning mock..."

# Create dummy artifacts
mkdir -p certs
echo "-----BEGIN MOCK KEY-----" > signing_key.pem
echo "1234" > handle.txt

# Test parameter handling
if [[ "$*" == *"--test-mode"* ]]; then
  echo "Test mode enabled"
  echo "additional_file.txt" > artifact.txt
fi

# Simulate success/failure
if [[ "$1" == "--fail" ]]; then
  echo "Provisioning failed!" >&2
  exit 1
fi

echo "Provisioning completed successfully"
exit 0