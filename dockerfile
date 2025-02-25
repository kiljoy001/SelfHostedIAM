FROM ubuntu:25.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    swtpm \
    tpm2-tools \
    tpm2-abrmd \           
    libtss2-* \               
    gnutls-bin 

# Create TPM simulator state and FAPI directories
RUN mkdir -p /tpmdata \
    && mkdir -p /etc/tpm2-tss \
    && mkdir -p ~/.local/share/tpm2-tss \
    && chmod 777 /tpmdata

# Copy FAPI configuration (create this file locally first)
COPY fapi-config.json /etc/tpm2-tss/fapi-config.json
COPY tpm /tpm

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
