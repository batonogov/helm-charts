// Global ("self-hosted") Renovate configuration consumed by the
// `.github/workflows/renovate.yaml` GitHub Actions run.
//
// This is NOT the per-repository config. The repository's own config is the
// repo-root `renovate.json`, which Renovate reads automatically when it
// processes the repo. This file only tells the self-hosted bot which
// platform/repository to touch and disables onboarding.
//
// Required secret: `RENOVATE_TOKEN` — a GitHub PAT (classic, `repo` scope for
// public+private capable access, or `repo:public_repo` for public repos only).
// The workflow's `GITHUB_TOKEN` MUST NOT be used: PRs it authors do not trigger
// downstream `pull_request` CI runs, which would leave Renovate PRs un-linted.
module.exports = {
  platform: 'github',
  repositories: ['batonogov/helm-charts'],
  // renovate.json already exists at the repo root — skip the onboarding PR.
  onboarding: false,
  // Don't hard-fail if a repository happens to have no config file.
  requireConfig: 'optional',
  // Distinct branch prefix so GHA-driven branches never collide with the
  // Renovate GitHub App, should it ever be enabled alongside this workflow.
  branchPrefix: 'renovate-gha/',
};
