# Use Ubuntu 22.04 as the base image
FROM fedora:39

# Install dependencies
RUN dnf install -y tpm2-tss tpm2-tss-fapi python3-pip pkg-config tpm2-tss-devel \
    python3-devel swtpm tpm2-abrmd dbus-daemon nmap-ncat pipenv tpm2-tss-engine
RUN dnf groupinstall -y 'Development Tools'
RUN dnf clean all

# Install tpm2-pytss (Python bindings)
RUN pip3 install tpm2-pytss

# Configure FAPI
RUN mkdir -p /etc/tpm2-tss/fapi-profiles \
    && echo '{"profile_name": "P_RSA"}' > /etc/tpm2-tss/fapi-profiles/P_RSA.json

# Copy config file for abrmd to container
COPY tpm2-abrmd.conf /etc/dbus-1/system.d/

# Create a directory for your code
WORKDIR /app
COPY tpm /app
COPY Pipfile /app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]