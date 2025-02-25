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
until [ -S /tpmdata/tpm2-simtpm.sock ]; do sleep 1; done
until nc -z localhost 2321; do sleep 1; done

# Initialize the TPM
tpm2_startup -c

#run test
python3 /test_tpm2.py

# Drop into an interactive shell
exec tail -f /dev/null