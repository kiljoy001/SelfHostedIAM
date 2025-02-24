#!/bin/bash

# Start the TPM simulator (swtpm) in the background
swtpm socket \
  --tpmstate dir=/tpmdata \
  --ctrl type=tcp,port=2322 \
  --server type=tcp,port=2321 \
  --flags not-need-init \
  --tpm2 &

# Wait for the simulator to start
sleep 1

# Start the TPM2 Access Broker/Resource Manager (abrmd)
tpm2-abrmd \
  --tcti=swtpm:host=localhost,port=2321 \
  --allow-root \
  --daemon &

# Wait for abrmd to start
sleep 1

# Initialize the TPM
tpm2_startup -c

# Drop into an interactive shell
exec /bin/bash