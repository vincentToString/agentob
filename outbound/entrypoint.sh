#!/bin/sh
set -e

if [ -n "$GITHUB_PRIVATE_KEY_PEM" ]; then
  # Added '--' below to safely handle the dashes in the PEM key
  printf -- "$GITHUB_PRIVATE_KEY_PEM" > /tmp/github-app-private-key.pem
  chmod 600 /tmp/github-app-private-key.pem
  export GITHUB_PRIVATE_KEY_PATH=/tmp/github-app-private-key.pem
fi

exec "$@"