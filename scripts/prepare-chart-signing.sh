#!/usr/bin/env bash
# Prepare an isolated legacy OpenPGP keyring for Helm/chart-releaser.
set -euo pipefail
umask 077

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_ENV:?GITHUB_ENV is required}"
: "${GPG_PRIVATE_KEY:?Configure the GPG_PRIVATE_KEY Actions secret}"
: "${GPG_PASSPHRASE:?Configure the GPG_PASSPHRASE Actions secret}"
: "${GPG_KEY_NAME:?Configure the GPG_KEY_NAME Actions variable}"
: "${GPG_KEY_FINGERPRINT:?Configure the GPG_KEY_FINGERPRINT Actions variable}"

# Values written to GITHUB_ENV must each fit on one line.
if [[ "$GPG_KEY_NAME" == *$'\n'* || "$GPG_KEY_NAME" == *$'\r'* || ! "$GPG_KEY_FINGERPRINT" =~ ^[A-Fa-f0-9]{40}$ ]]; then
  echo "Invalid signing key name or fingerprint" >&2
  exit 1
fi

signing_dir="$RUNNER_TEMP/chart-signing"
mkdir -m 700 "$signing_dir"
# Keep the agent socket path short enough for macOS as well as Linux.
export GNUPGHOME
GNUPGHOME=$(mktemp -d "${TMPDIR:-/tmp}/helm-gpg.XXXXXX")
cleanup() {
  gpgconf --kill gpg-agent || true
  rm -rf -- "$GNUPGHOME"
}
trap cleanup EXIT

printf '%s\n' "$GPG_PRIVATE_KEY" | gpg --batch --import
printf '%s' "$GPG_PASSPHRASE" > "$signing_dir/passphrase"
gpg --batch --yes --pinentry-mode loopback \
  --passphrase-file "$signing_dir/passphrase" \
  --export-secret-keys "$GPG_KEY_FINGERPRINT" > "$signing_dir/secring.gpg"
gpg --batch --export "$GPG_KEY_FINGERPRINT" > "$signing_dir/pubring.gpg"
gpg --batch --armor --export "$GPG_KEY_FINGERPRINT" > "$signing_dir/public-key.asc"
test -s "$signing_dir/secring.gpg"
test -s "$signing_dir/pubring.gpg"

# Fail before publication if Helm cannot use this key or passphrase.
mkdir "$signing_dir/probe"
printf 'apiVersion: v2\nname: signing-probe\nversion: 0.1.0\n' > "$signing_dir/probe/Chart.yaml"
helm package "$signing_dir/probe" --destination "$signing_dir" --sign \
  --key "$GPG_KEY_NAME" --keyring "$signing_dir/secring.gpg" \
  --passphrase-file "$signing_dir/passphrase"
helm verify "$signing_dir/signing-probe-0.1.0.tgz" --keyring "$signing_dir/pubring.gpg"

{
  echo 'CR_SIGN=true'
  echo "CR_KEY=$GPG_KEY_NAME"
  echo "CR_KEYRING=$signing_dir/secring.gpg"
  echo "CR_PASSPHRASE_FILE=$signing_dir/passphrase"
} >> "$GITHUB_ENV"
