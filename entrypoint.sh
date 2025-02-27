#!/bin/bash

# Permission to use dbus
mkdir -p /var/run/dbus
dbus-daemon --system --nofork &

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
  --allow-root &

# Wait for abrmd to start
until nc -z localhost 2321; do sleep 1; done

# Initialize the TPM
tpm2_startup -c

# Enable Pipenv
pipenv install Pipfile 
chmod +x tpm_provisioning.sh
pipenv shell

# Drop into an interactive shell
exec /bin/bash