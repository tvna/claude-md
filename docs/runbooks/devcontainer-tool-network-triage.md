# Devcontainer Tool Network Triage Runbook

This runbook is the deliverable for
[#1170](https://github.com/tvna/claude-md/issues/1170), under parent
[#696](https://github.com/tvna/claude-md/issues/696). It defines the
repeatable procedure for evaluating a new tool's network behavior before
that tool's outbound destinations are admitted to the devcontainer egress
allowlist.

The devcontainer egress posture is deny-by-default (see the Egress allowlist
section of [`devcontainers.md`](devcontainers.md)): a destination is admitted
only by adding a hostname to `.devcontainer/network/*.allowlist`. Without a
fixed method, each new tool forced an ad-hoc "which hosts, and are they
trustworthy" judgement. This runbook replaces that per-tool cost with one
observe -> evaluate -> decide -> verify procedure, and the
`scripts/scan_allowlist_rationale.py` gate makes the recorded decision a
deterministic precondition for every host entry.

Treat a new tool's network reach as a supply-chain input, the same way
[`agent-provenance.md`](agent-provenance.md) treats a skill or MCP server.
This runbook is the network-destination counterpart of that provenance
review.

## Scope

This runbook applies whenever a change introduces or updates a devcontainer
tool that may reach the network at runtime, including:

- A CLI added to `flake.nix` and linked into the container.
- A tool whose new subcommand or version contacts a new endpoint.
- Any provisioned tool whose runtime traffic is not already covered by an
  existing allowlist host.

Build-time-only network access does not need an allowlist entry. Per
[`devcontainer-tooling.md`](../standards/devcontainer-tooling.md), a tool
fetched by a `fetchurl` derivation reaches the network only during the Nix
build; only runtime destinations are allowlisted. Decide which case applies
before observing.

CI-only note: the observation and verification steps below run inside the
devcontainer and require `NET_ADMIN`, `iptables`, and the `nix develop
.#network` shell. They cannot run in the Claude Code on the Web environment.
Do not record their results as done unless they were actually run in a
container; mark them `deferred to CI / container` otherwise.

## Observe

Goal: enumerate the DNS names and HTTP/HTTPS destinations the candidate tool
actually contacts at runtime, using only tools already provisioned in the
`nix develop .#network` shell (`dnsutils`, `iproute2`, `iptables`).

1. Enforced-mode discovery (cheapest). Leave the allowlist applied, then run
   the tool's representative workflow. Destinations the tool needs but that
   are not yet allowed surface as connection failures or timeouts. Confirm
   each suspected host resolves and is reachable:

   ```sh
   getent hosts <host>
   dig +trace <host>
   curl -I --max-time 20 https://<host>
   ```

   Record only the status line and `cf-ray` / `cf-mitigated` headers, never
   `Set-Cookie` or token-bearing headers (mirrors the diagnostic discipline
   in [`devcontainers.md`](devcontainers.md)).

2. Audit-mode discovery (more complete). When enforced-mode failures do not
   reveal the full destination set, capture outbound attempts with an
   `iptables` LOG rule inside `nix develop .#network`, run the tool's
   representative workflow with enforcement disabled for that one container
   start (`DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0`), then read the logged
   destination IPs from the kernel log and reverse-resolve them to hostnames.
   This temporarily widens egress and is diagnosis only; never leave the
   audit rule or the disabled enforcement in place.

3. Separate facts from speculation. A host you observed the tool contact is a
   fact; a host you expect it might contact is speculation. Tag each
   accordingly when you record the destination set.

## Evaluate

For every observed destination, collect the following before deciding. This
table is the network-endpoint translation of the provenance metadata table in
[`agent-provenance.md`](agent-provenance.md). If a field is unknown, mark it
`unknown` and state why; do not fill it with speculation.

| Field | Evidence / how to collect | Tool |
|---|---|---|
| Hostname | The destination from the Observe step. | - |
| Resolution chain | The A/CNAME chain and what it actually points at (CDN, cloud bucket, vendor origin). | `dig +trace <host>`, `getent ahostsv4 <host>` |
| Operator / owner | Domain and IP ownership; name the reviewable operator, not only a brand. | RDAP / WHOIS (run from the host or during audit mode, since egress is otherwise blocked) |
| Purpose | Why the tool contacts the host; cite the vendor documentation. | Manual |
| Build-time vs runtime | Whether the host is reached only during the Nix build (no allowlist) or at runtime (allowlist). | The distinction in [`devcontainer-tooling.md`](../standards/devcontainer-tooling.md) |
| Necessity | Whether the host is core to the tool's function or optional telemetry, and whether it can be disabled. | Manual |
| Threat-intel signal | Typosquat, recently registered domain, known-malicious history, or other intelligence. | Manual; map to the threat-label semantics below |
| Decision | allow / deny / defer, and the target file (`shared` vs the agent-specific allowlist). | Recorded as an inline rationale comment |

Threat-intel signals map onto the existing label semantics in
[`label-taxonomy.md`](../standards/label-taxonomy.md): any finding that needs
investigation before routing is `threat:intel-needed`; a destination with a
confirmed known-exploited or malware association is `threat:response-needed`
and blocks admission until response planning occurs.

## Review Questions

These are hard blockers, adapted from the provenance review questions. A
"yes" to a risk question requires a named mitigation in the PR body before
the destination is admitted.

1. Is the destination operator identifiable and reviewable, or only an opaque
   IP?
2. Is the connection actually required at runtime, or is it build-time only
   (and therefore not an allowlist entry at all)?
3. Is the destination scoped to the narrowest host the tool needs, rather
   than a broad parent domain?
4. Could the tool send secrets, tokens, environment variables, or repository
   context to this destination? If so, name the mitigation (disable the
   feature, scope the token, or reject the tool).
5. Is there any threat-intel signal? If so, apply `threat:intel-needed`
   (or `threat:response-needed` for a confirmed exploited / malware
   association) and do not admit until it is resolved.

## Decision and Record

- Admit: add the hostname to the correct allowlist file -- `shared.allowlist`
  when both agents need it, or the agent-specific
  `claude.allowlist` / `codex.allowlist` -- with an inline trailing rationale
  comment:

  ```
  api.example.com  # Why this destination is required at runtime.
  ```

  The inline `#` is stripped by `.devcontainer/scripts/apply-egress-allowlist.sh`
  and by `tests/test_devcontainer_allowlist.py`, so the rationale never
  changes the resolved host set.

- Reject: do not add the host; record in the PR or issue why the tool was not
  adopted (for example, an unnecessary telemetry endpoint that cannot be
  disabled).

- Defer: when evidence is incomplete, keep the tool out of the container and
  open or update a tracked follow-up that names the missing evidence.

## Verification

- Re-run the tool's representative workflow with the allowlist enforced and
  only the approved hosts present; confirm the tool succeeds. (Container /
  CI only.)
- Run the deterministic rationale gate so no host can be admitted without a
  recorded decision:

  ```sh
  python3 scripts/scan_allowlist_rationale.py verify
  ```

- Confirm the allowlist still parses and the resolved host set is what you
  intended:

  ```sh
  bash -n .devcontainer/scripts/apply-egress-allowlist.sh
  ```

## Rollback

Prefer `git revert` of the commit that admitted the destination (see
[`revert-first-rollback.md`](revert-first-rollback.md)). When a single host
must be removed, delete its line from the allowlist file; the next container
start re-applies the narrower rule set. Removing a host is safe-by-default:
it can only tighten egress, never widen it.

## References

- [`devcontainers.md`](devcontainers.md) -- devcontainer entrypoints and the
  Egress allowlist operational section.
- [`devcontainer-tooling.md`](../standards/devcontainer-tooling.md) --
  provisioning standard and the build-time vs runtime distinction; the
  rationale gate is registered there.
- [`agent-provenance.md`](agent-provenance.md) -- provenance metadata and
  review-question template this runbook adapts for network destinations.
- [`label-taxonomy.md`](../standards/label-taxonomy.md) -- `threat:*` label
  semantics used in the Evaluate step.
- Gate: `scripts/scan_allowlist_rationale.py`; tested by
  `tests/test_scan_allowlist_rationale.py`.
