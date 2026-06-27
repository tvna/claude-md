# SSH Commit Signing; Developer Setup Runbook

This runbook covers setup for SSH commit signing on local feature branches
in devcontainer and macOS environments.
It is a companion to [`docs/standards/commit-signing.md`](../standards/commit-signing.md),
which defines the normative contract for `required_signatures` on `main`.
The standard's keyless invariant (GitHub squash-merge signature on `main`)
is unchanged; this runbook adds optional client-side signing for
feature branches. Refs [#1789](https://github.com/tvna/claude-md/issues/1789).

## Why this runbook exists

GitHub's `required_signatures` rule on `main` is satisfied by GitHub's
squash-merge web-flow signature; unsigned feature-branch commits are fine.
Client-side SSH signing gives developers `Verified` badges on feature-branch
commits (useful under Vigilant Mode and for supply-chain hygiene) and is now
automated for devcontainer and macOS `nix develop` environments via Nix.

Claude Code Web sessions are excluded: those commits carry
`noreply@anthropic.com` as committer identity, which is not a GitHub account
with a registered signing key. Those commits are intentionally unsigned on
their branch; the normative rationale is in
[`docs/standards/commit-signing.md`](../standards/commit-signing.md).

## Prerequisites; Register an SSH Signing Key on GitHub

SSH signing requires a *Signing* key registered on GitHub, **separate** from
the authentication key used for `git push`. The same public key may be
registered for both roles.

1. Open [github.com/settings/keys](https://github.com/settings/keys).
2. Click **New SSH key**.
3. Set **Title** to something identifiable (e.g., `MacBook Pro; signing`).
4. Set **Key type** to **Signing Key** (not Authentication Key).
5. Paste the content of the public key (e.g., `~/.ssh/id_ed25519.pub`).
6. Click **Add SSH key**.

No GitHub-enforced expiry. Rotate when the private key is compromised or the
machine is decommissioned; remove the old Signing Key from
[github.com/settings/keys](https://github.com/settings/keys) and re-register.

## Devcontainer setup (automated)

The setup runs in two phases: a HOST-side `initializeCommand` step that
isolates the public keys, and a container-side `postCreateCommand` step that
writes the git config.

### Host-side key preparation (`initializeCommand`)

`initializeCommand` in each `devcontainer.json` calls
`.devcontainer/scripts/prepare-signing-keys.sh` on the **host**, before the
container starts. That script:

1. Creates `~/.ssh/devcontainer-signing-keys/` on the host (mode `700`).
2. Copies only `id_ed25519.pub`, `id_rsa.pub`, and `id_ecdsa.pub` into that
   subdirectory; private keys are never copied.
3. Exits 0 even when no public keys are found.

The `mounts` entry in each `devcontainer.json` binds **only** that
`devcontainer-signing-keys` subdirectory into the container at
`~/.ssh/devcontainer-signing-keys` (read-only). This means no private key
material ever enters the container, regardless of the agent user's UID.

### Container-side git config (`postCreateCommand`)

`postCreateCommand` calls `configure-agent-runtime.sh`, which runs
`.devcontainer/scripts/configure-git-signing.sh`. That script:

1. Searches `~/.ssh/devcontainer-signing-keys/` for `id_ed25519.pub`,
   `id_rsa.pub`, or `id_ecdsa.pub` (first match wins).
2. Writes `gpg.format = ssh`, `user.signingKey`, and `commit.gpgsign = true`
   into `~/.gitconfig` via `git config --file`.
3. Exits 0 and emits `INFO: no SSH public key found` when the directory is
   empty; the container is fully functional without signing.

### Verify devcontainer signing

After reopening the container:

```sh
git config --list --global | grep -E 'gpg|signing'
```

Expected output:

```
gpg.format=ssh
user.signingkey=/home/claude/.ssh/devcontainer-signing-keys/id_ed25519.pub
commit.gpgsign=true
```

Confirm a commit is signed:

```sh
git log --show-signature -1
```

`Good "git" signature for <your-email>` means the private key is present and
the signature is valid. GitHub shows `Verified` when the email also matches a
GitHub account that registered the Signing Key.

## macOS setup (nix develop)

Run from the repository root:

```sh
nix develop
```

The `default` devShell `shellHook` for `aarch64-darwin` and `x86_64-darwin`
(added in `flake.nix`) auto-detects the first SSH public key in `~/.ssh/` and
sets git signing **for the local repository only** (`git config --local`),
leaving the global git config untouched.

### Verify macOS signing

```sh
git config --list --local | grep -E 'gpg|signing'
```

Expected output:

```
gpg.format=ssh
user.signingkey=/Users/you/.ssh/id_ed25519.pub
commit.gpgsign=true
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `INFO: no SSH public keys found` in initializeCommand logs | `id_ed25519.pub`, `id_rsa.pub`, and `id_ecdsa.pub` all absent from host `~/.ssh/` | Generate a key (`ssh-keygen -t ed25519`) on the host and re-open the container |
| `INFO: no SSH public key found` in postCreateCommand logs | `~/.ssh/devcontainer-signing-keys/` is empty (initializeCommand found no keys) | Check host `~/.ssh/` for `.pub` files; see row above |
| `git log --show-signature` shows `BAD signature` | Private key does not match the configured public key | Run `git config user.signingKey` and compare with the registered Signing Key on GitHub |
| GitHub shows `Unverified` | `user.email` in git config does not match a GitHub account with the Signing Key registered | `git config --global user.email your@email.com` (must match GitHub account email) |
| `nix develop` shellHook does nothing on macOS | Shell started outside a git repository | `cd` to the repository root before running `nix develop` |
| Signing key path changes after re-keying | `~/.gitconfig` retains the old key path | Re-run `prepare-signing-keys.sh` on the host then re-open the container, or set: `git config --global user.signingKey ~/.ssh/devcontainer-signing-keys/id_ed25519.pub` |

## Recovery: an already-pushed unsigned commit on a protected branch

A remote agent session can leave an unsigned commit on a `claude/*` session
branch (a cold signer early in the session, or a `git merge origin/main`
ancestor from the no-rebase base-update path). Because the `all-branches`
ruleset blocks `non_fast_forward` and `deletion` with `bypass_actors: []`,
that commit can be neither re-signed nor rewritten out in place. This is the
PR #2103 condition (retro #2114 / signing defect #2116). Do **not** attempt to
provision a signing key into the session and re-sign: a session committer
identity (`noreply@anthropic.com`) is not a GitHub account with a registered
signing key, so the result is still `Unverified` and does not satisfy
`required_signatures`.

The keyless invariant makes this recoverable without touching the ruleset.
Pick the first option that applies (full detail in
[`docs/standards/commit-signing.md`](../standards/commit-signing.md), "Web /
remote agent sessions", unsigned-ancestor exception):

1. **Squash-merge as normal.** When the only unsigned objects are the commits
   being squashed, GitHub's squash commit on `main` is web-flow `Verified` and
   satisfies `required_signatures`; the merge-box "Commits must have verified
   signatures" warning does not block the squash-merge API. PR #2103 was
   recovered this way.
2. **Repo-admin `--admin` override** (only when an unsigned *ancestor* makes
   the merge box block the squash): `gh pr merge <pr> --squash --admin`, after
   independently confirming the PR is otherwise ready (checks green, threads
   resolved, code-owner review, exact head SHA). `--admin` clears the signature
   block only; GitHub still signs the squash commit web-flow.
3. **Recreate the branch off current `main`** (no admin available): drop the
   stale unsigned ancestor by re-creating the branch or opening a replacement
   PR. The recreated feature commits follow the normal keyless path.

The deterministic guards that surface this *before* the irreversible push are
`scripts/check_commit_signing_ready.py` (SessionStart warning plus a PreToolUse
block on every commit-producing command when a live test-sign comes back
unsigned) and `scripts/gate_unsigned_commit_bash.py` (denies an inline
signing-bypass flag).
