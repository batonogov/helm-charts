#!/usr/bin/env bash
# Exercise the real Helm signing path using a disposable, password-protected key.
set -euo pipefail
umask 077

test_dir=$(mktemp -d)
export GNUPGHOME="$test_dir/source-gnupg"
cleanup() {
  gpgconf --kill gpg-agent || true
  rm -rf -- "$test_dir"
}
trap cleanup EXIT
mkdir -m 700 "$GNUPGHOME"
export GPG_KEY_NAME='Chart Signing Test <chart-signing@example.invalid>'
export GPG_PASSPHRASE='disposable-test-passphrase'
gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" \
  --quick-generate-key "$GPG_KEY_NAME" rsa2048 sign 1d
export GPG_KEY_FINGERPRINT
GPG_KEY_FINGERPRINT=$(gpg --batch --with-colons --list-secret-keys | awk -F: '$1 == "fpr" {print $10; exit}')
export GPG_PRIVATE_KEY
GPG_PRIVATE_KEY=$(gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" \
  --armor --export-secret-keys "$GPG_KEY_FINGERPRINT")

export RUNNER_TEMP="$test_dir/valid"
export GITHUB_ENV="$test_dir/github-env"
mkdir "$RUNNER_TEMP"
bash scripts/prepare-chart-signing.sh
while IFS='=' read -r name value; do
  export "$name=$value"
done < "$GITHUB_ENV"
[[ "$CR_SIGN" == true ]]

# Use the exact options passed to chart-releaser, then detect tampering.
helm package "$RUNNER_TEMP/chart-signing/probe" --destination "$test_dir" \
  --sign --key "$CR_KEY" --keyring "$CR_KEYRING" --passphrase-file "$CR_PASSPHRASE_FILE"
helm verify "$test_dir/signing-probe-0.1.0.tgz" --keyring "$RUNNER_TEMP/chart-signing/pubring.gpg"
printf 'tampered' >> "$test_dir/signing-probe-0.1.0.tgz"
if helm verify "$test_dir/signing-probe-0.1.0.tgz" --keyring "$RUNNER_TEMP/chart-signing/pubring.gpg"; then
  echo 'Tampered package was accepted' >&2
  exit 1
fi

expect_failure() {
  export RUNNER_TEMP="$test_dir/$1"
  export GITHUB_ENV="$test_dir/$1-env"
  mkdir "$RUNNER_TEMP"
  if bash scripts/prepare-chart-signing.sh > "$test_dir/$1.log" 2>&1; then
    echo "Unexpected signing success: $1" >&2
    exit 1
  fi
  if [[ -s "$GITHUB_ENV" ]]; then
    echo "Signing configuration exported after failure: $1" >&2
    exit 1
  fi
}

(export GPG_PRIVATE_KEY=''; expect_failure missing-key)
(export GPG_PASSPHRASE='incorrect'; expect_failure wrong-passphrase)
(export GPG_KEY_FINGERPRINT='0000000000000000000000000000000000000000'; expect_failure wrong-fingerprint)
(export GPG_KEY_NAME='nonexistent identity'; expect_failure wrong-identity)
echo 'Chart signing checks passed'
