#!/bin/bash

# Set default locale if not specified
export LANG=${LANG:-en_US.UTF-8}
export LC_ALL=${LC_ALL:-en_US.UTF-8}

# Install RabbitMQ first
echo "🐇 Installing RabbitMQ..."
chmod +x install_rabbitmq.sh  # Fix permission issue
./install_rabbitmq.sh

# Start RabbitMQ server in container-friendly way
echo "🚀 Starting RabbitMQ..."
/usr/sbin/rabbitmq-server start &

# After starting RabbitMQ
echo "⏳ Waiting for RabbitMQ to start..."
until rabbitmqctl status >/dev/null 2>&1; do
  sleep 1
done
echo "✅ RabbitMQ is ready!"

# Permission to use dbus
mkdir -p /var/run/dbus
dbus-daemon --system --nofork &

# Wait for DBus socket
echo "⏳ Waiting for DBus to be ready..."
until [ -S /var/run/dbus/system_bus_socket ]; do
  sleep 1
done
echo "✅ DBus is ready!"

# Start the TPM simulator (swtpm) in the background
echo "🔐 Starting SWTPM..."
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

# Verify ABRMD registration
until busctl list | grep -q com.intel.tss2.Tabrmd; do
  echo "⏳ Waiting for tpm2-abrmd registration..."
  sleep 1
done

# Wait for abrmd to start
until nc -z localhost 2321; do sleep 1; done
echo "✅ SWTPM is ready!"

# Initialize the TPM
tpm2_startup -c

# Enable Pipenv
if [ -n "$DEV_MODE" ]; then
    echo "🛠️  Running in DEVELOPMENT mode"
    INSTALL_CMD="pipenv install Pipfile --dev"
    PYTEST_CMD="pytest /tests"
else
    echo "🚀 Running in PRODUCTION mode"
    INSTALL_CMD="pipenv install Pipfile"
    PYTEST_CMD="true"  # No-op for production
fi
echo "📦 Installing dependencies..."
eval $INSTALL_CMD

chmod +x tpm_provisioning.sh tpm_self_signed_cert.sh tpm_random_number.sh
chmod +x /tests/mock_scripts/*.sh
pipenv shell

