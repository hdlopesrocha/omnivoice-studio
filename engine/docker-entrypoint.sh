#!/bin/sh
set -e

# Empty Compose values should behave like unset values for Hugging Face.
[ -n "${HF_TOKEN:-}" ] || unset HF_TOKEN
[ -n "${HF_ENDPOINT:-}" ] || unset HF_ENDPOINT

# The container starts as root so a fresh named volume (or a bind mount)
# can be made writable by the unprivileged runtime user.
mkdir -p /data /data/hf /data/voices /data/outputs

if [ "$(id -u)" = "0" ]; then
    # Always fix the top-level directories. Directories added in a newer
    # version (for example /data/tmp) must not remain root-owned on an
    # existing volume.
    chown appuser:appuser /data /data/hf /data/voices /data/outputs

    # Uploaded job files are disposable and no job can survive a restart.
    rm -rf /data/tmp
    mkdir -p /data/tmp
    chown appuser:appuser /data/tmp

    # Do the expensive recursive ownership fix once per volume: the
    # Hugging Face cache can contain thousands of files.
    if [ ! -f /data/.appuser-owned ]; then
        chown -R appuser:appuser /data
        touch /data/.appuser-owned
        chown appuser:appuser /data/.appuser-owned
    fi
    exec gosu appuser "$@"
fi

exec "$@"
