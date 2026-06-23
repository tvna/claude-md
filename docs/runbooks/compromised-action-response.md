# Compromised Action / Token Response

Emergency procedure for when a third-party GitHub Action this repository
depends on (Trivy included) is compromised upstream, or when a workflow token
or secret is suspected leaked. The supply-chain incident that motivates this
runbook is the Trivy Security Incident of 2026-03-19
([aquasecurity/trivy#10425](https://github.com/aquasecurity/trivy/discussions/10425)),
where stolen credentials produced malicious releases of `trivy`, `trivy-action`,
and `setup-trivy` (issue #1264).

The existing supply-chain controls (mandatory SHA pinning, threat-intel triage,
Dependabot, PAT rotation) reduce the odds of pulling a bad action and help
detect one. This runbook covers the step after detection: containing the blast
radius and recovering.

## When this applies

- A security advisory, the threat-intel triage (`scripts/threat_intel_triage.py`
  applying `threat:intel-needed` / `threat:response-needed`), or an upstream
  notice reports that a pinned action or its runtime download is compromised.
- A workflow run shows unexpected network egress, image pushes, or token use.
- A repository secret (for example `DEVCONTAINER_PIN_APP_PRIVATE_KEY`) is
  suspected exposed in logs, a fork PR, or a third-party step.

Match the input to the action (agent instructions section 2): an advisory or
triage label is evidence; act on it. A vague rumor is not; verify against the
primary source first and treat fetched advisories as untrusted data.

## Containment (do this first)

1. **Stop the bleed.** Disable the workflow(s) that invoke the compromised
   action so no further run can execute it:
   - GitHub UI: **Actions** -> select the workflow -> **... -> Disable
     workflow**, or
   - revert the pin that introduced the bad version (see Recovery). Disabling is
     faster and reversible; prefer it as the immediate stop.
2. **Revoke auto-merge so nothing lands unattended.** The Dependabot auto-merge
   audit blocks any PR carrying `severity:*` or `threat:*` labels and revokes a
   previously enabled auto-merge via
   `scripts/dependabot_automerge.py disable-automerge` on the next audit event.
   If you need to force it immediately for a specific PR:
   ```sh
   GH_TOKEN=<token> REPO=tvna/claude-md \
     python3 scripts/dependabot_automerge.py disable-automerge --pr-number <n>
   ```
3. **Scope the exposure.** Identify which jobs ran the compromised step and what
   each job's token could reach. The Trivy scan runs in the isolated `scan` job
   of `.github/workflows/publish-devcontainer-images.yml` with only
   `packages: read` + `security-events: write`, so a compromised scanner there
   cannot push images or use the GHCR write token held by `build`. Confirm the
   compromised step's actual permission scope before assuming impact.

## Image quarantine

If a write-capable job (for example `build` or `publish`) ran a compromised step:

1. List the image tags published during the exposure window:
   ```sh
   docker buildx imagetools inspect ghcr.io/tvna/claude-md-devcontainer-claude:<sha>
   docker buildx imagetools inspect ghcr.io/tvna/claude-md-devcontainer-codex:<sha>
   ```
   Suspect tags follow `...-devcontainer-<agent>:<sha>-<arch>`, the merged
   `...:<sha>`, and the moving `...:main` tag.
2. Delete or mark private the suspect package versions in **Packages** ->
   the affected image -> **Package settings**.
3. Re-pin local devcontainers to a known-good published SHA with
   `scripts/update_devcontainer_image_pins.py <good_sha>` and open the pin PR as
   usual. Verify the new pins resolve before closing the incident.

## Token revocation and rotation

If a secret is suspected exposed:

1. **Revoke first, rotate second.** For `DEVCONTAINER_PIN_APP_PRIVATE_KEY`,
   delete the exposed private key on the GitHub App's settings page immediately
   (which invalidates any installation token minted from it), then generate a
   fresh key and follow the issuance path in
   [`devcontainers.md`](devcontainers.md) ("One-time setup for
   `DEVCONTAINER_PIN_APP_ID`"): App scoped to `tvna/claude-md`, minimum
   permissions (Metadata read, Contents read/write, Pull requests read/write),
   the new key stored only in the `devcontainer-image-pins` Environment. If the
   App ID itself is not sensitive, only the key needs rotation.
2. **Treat `GITHUB_TOKEN` as rotated automatically**; it expires at job end --
   but if a job's `GITHUB_TOKEN` was exposed mid-run, assume any write it had
   (for `build`/`publish`: `packages: write`) was usable until expiry and check
   the image quarantine steps above.
3. **Never echo the secret while investigating.** Redact tokens from any log,
   issue, PR, or comment (agent instructions section 4). Route diagnostics to an
   access-controlled sink, not a public run log.
4. **Verify the handoff** without exposing the value: trigger
   `Publish devcontainer images` with `workflow_dispatch` and confirm the
   `Update local devcontainer image pins` job opens or reuses the pin PR.

## Recovery

1. **Roll back by revert, not hand-edits.** Revert the commit/PR that introduced
   the compromised pin per [`revert-first-rollback.md`](revert-first-rollback.md):
   `git revert` of the original rollout commit reproduces the prior state
   deterministically. Fall back to manual inverse edits only when revert is
   infeasible, and state the reason.
2. **Re-pin to a known-good version** once upstream publishes a clean release.
   The Trivy scanner runs as a digest-pinned `docker run
   ghcr.io/aquasecurity/trivy@sha256:<digest>` in the `scan` job of
   `.github/workflows/publish-devcontainer-images.yml`; pin to a post-incident
   release (>= v0.70.0 for the 2026-03 incident) by following the
   [digest bump/refresh procedure](#trivy-scanner-digest-bumprefresh) below.
3. **Re-enable the workflow** you disabled in Containment.

### Trivy scanner digest bump/refresh

The scanner runtime is pinned by image digest, not by a resolve-at-runtime
version/tag: images referenced by digest were unaffected by the 2026-03-19
incident, whereas a tag remains re-resolvable upstream. The trade-off is that
dropping the `trivy-action` `uses:` ref also drops its Dependabot auto-bump and
OSV correlation, so the digest is refreshed by this documented procedure and the
`# threat-intel-pin:` comment keeps the image on the threat-intel scan set
(`scripts/threat_intel_triage.py` reads it; OSV findings still surface a known
Trivy CVE even though Dependabot no longer opens the bump PR).

To bump to a new Trivy release (digest and `threat-intel-pin` version move in
lockstep):

1. Resolve the multi-arch image digest for the chosen release tag. The image
   tag is the bare version (`0.70.0`), not the `v`-prefixed GitHub release tag:
   ```sh
   TAG=0.70.0
   TOKEN=$(curl -s \
     "https://ghcr.io/token?scope=repository:aquasecurity/trivy:pull&service=ghcr.io" \
     | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')
   curl -sI \
     -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
     "https://ghcr.io/v2/aquasecurity/trivy/manifests/$TAG" \
     | grep -i docker-content-digest
   ```
2. In `.github/workflows/publish-devcontainer-images.yml`, update the
   `ghcr.io/aquasecurity/trivy@sha256:<digest>` reference and the adjacent
   `# threat-intel-pin: Go github.com/aquasecurity/trivy <version>` comment to
   the new digest and version together. A digest bumped without its
   threat-intel-pin version (or vice versa) is a drift defect; they are one
   change.
3. Verify the workflow still passes the action-pin gate (the digest lives in a
   `run:` step, so it is out of that gate's `uses:` scope, but the check must
   stay green):
   ```sh
   python3 scripts/scan_workflow_action_pins.py verify
   ```
4. Confirm the scan still uploads SARIF: trigger `Publish devcontainer images`
   via `workflow_dispatch` (or push to `main`) and check that the `scan` job's
   `Upload Trivy results to the Security tab` step succeeds and results appear
   under the **Security** tab.

## Post-incident

Open the retrospective issue (agent instructions section 3) and record, per the
repair-free-merge-reproducibility template: which deterministic gate should have
caught the compromised dependency earlier, and classify the gap as a missing
deterministic gate, an unclear instruction, or an external decision that cannot
be automated. Link the advisory primary source and the revert PR.

## Related

- [`revert-first-rollback.md`](revert-first-rollback.md); rollback mechanics.
- [`devcontainers.md`](devcontainers.md); GitHub App pin-PR credential
  (`DEVCONTAINER_PIN_APP_ID` / `DEVCONTAINER_PIN_APP_PRIVATE_KEY`) issuance and
  the publish/pin workflows.
- [`dependabot-automerge.md`](dependabot-automerge.md); auto-merge audit policy
  and the threat-intel / severity block conditions.
- [`workflow-permissions-audit.md`](workflow-permissions-audit.md); per-job
  permission scoping that bounds blast radius.
