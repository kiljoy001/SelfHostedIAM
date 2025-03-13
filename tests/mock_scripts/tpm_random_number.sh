#!/bin/bash
# Generates random data file
echo "Generating random data..."

DEFAULT_SIZE=32
size=${1:-$DEFAULT_SIZE}

if ! [[ "$size" =~ ^[0-9]+$ ]]; then
  echo "Invalid size parameter: $size" >&2
  exit 3
fi

if [ "$size" -gt 1024 ]; then
  echo "Size too large (max 1024)" >&2
  exit 4
fi

dd if=/dev/urandom of=tpm_random.bin bs=1 count=$size status=none

echo "Generated $size random bytes"
exit 0