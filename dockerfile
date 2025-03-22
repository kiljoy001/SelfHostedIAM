# Use fedora 41 as the base image
FROM fedora:41

# Install dependencies
RUN dnf install -y tpm2-tss tpm2-tss-fapi python3-pip pkg-config tpm2-tss-devel \
    python3-devel swtpm tpm2-abrmd dbus-daemon nmap-ncat tpm2-tss-engine openssl tpm2-openssl tpm2-tools \
    glibc-langpack-en glibc-locale-source
RUN dnf install -y @development-tools
RUN localedef -c -i en_US -f UTF-8 en_US.UTF-8
RUN dnf clean all

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PYTHONIOENCODING=UTF-8

# Install tpm2-pytss (Python bindings) & Pipenv
RUN pip3 install tpm2-pytss pipenv

# Copy config file for abrmd to container
COPY tpm2-abrmd.conf /etc/dbus-1/system.d/

# Create a directory for your code
WORKDIR /tpm
COPY tpm /tpm
COPY helper /helper
COPY Pipfile /tpm
COPY tests  /tests

# Set python path to root
ENV PYTHONPATH=/
# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh


ENTRYPOINT ["/entrypoint.sh"]