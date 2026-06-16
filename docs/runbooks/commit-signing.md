# SSH Commit Signing — Developer Setup Runbook

This runbook covers setup for SSH commit signing on local feature branches
in devcontainer and macOS environments.
It is a companion to [`docs/standards/commit-signing.md`](../standards/commit-signing.md),
which defines the normative contract for `required_signatures` on `main`.
The standard's keyless invariant (GitHub squash-merge signature on `main`)
is unchanged; this runbook adds optional client-side signing for
feature branches. Refs [#1789](https://github.com/tvna/claude-md/issues/1789).

## Why this runbook exists

GitHub's `required_signatures` rule on `main` is satisfied by GitHub's
squash-merge web-flow signature — unsigned feature-branch commits are fine.
Client-side SSH signing gives developers `Verified` badges on feature-branch
commits (useful under Vigilant Mode and for supply-chain hygiene) and is now
automated for devcontainer and macOS `nix develop` environments via Nix.

Claude Code Web sessions are excluded: those commits carry
`noreply@anthropic.com` as committer identity, which is not a GitHub account
with a registered signing key. Those commits are intentionally unsigned on
their branch; the normative rationale is in
[`docs/standards/commit-signing.md`](../standards/commit-signing.md).

## Prerequisites — Register an SSH Signing Key on GitHub

SSH signing requires a *Signing* key registered on GitHub, **separate** from
the authentication key used for `git push`. The same public key may be
registered for both roles.

1. Open [github.com/settings/keys](https://github.com/settings/keys).
2. Click **New SSH key**.
3. Set **Title** to something identifiable (e.g., `MacBook Pro -- signing`).
4. Set **Key type** to **Signing Key** (not Authentication Key).
5. Paste the content of the public key (e.g., `~/.ssh/id_ed25519.pub`).
6. Click **Add SSH key**.

No GitHub-enforced expiry. Rotate when the private key is compromised or the
machine is decommissioned; remove the old Signing Key from
[github.com/settings/keys](https://github.com/settings/keys) and re-register.

## Devcontainer setup (automated)

`postCreateCommand` in `.devcontainer/claude/devcontainer.json` and
`.devcontainer/codex/devcontainer.json` calls `configure-agent-runtime.sh`,
which runs `.devcontainer/scripts/configure-git-signing.sh`.

That script:

1. Searches `~/.ssh/` for `id_ed25519.pub`, `id_rsa.pub`, or `id_ecdsa.pub`
   (first match wins).
2. Writes `gpg.format = ssh`, `user.signingKey`, and `commit.gpgsign = true`
   into `~/.gitconfig` via `git config --file`.
3. Exits 0 and emits `INFO: no SSH public key found` when no key is present —
   the container is fully functional without signing.

The host `~/.ssh` directory is bind-mounted read-only at container build time
(`mounts` entry in each `devcontainer.json`). No private key material is
written inside the container.

### Verify devcontainer signing

After reopening the container:

```sh
git config --list --global | grep -E 'gpg|signing'
```

Expected output:

```
gpg.format=ssh
user.signingkey=/home/claude/.ssh/id_ed25519.pub
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
| `INFO: no SSH public key found` in postCreateCommand logs | `id_ed25519.pub`, `id_rsa.pub`, and `id_ecdsa.pub` all absent from host `~/.ssh/` | Generate a key (`ssh-keygen -t ed25519`) and re-create the container |
| `git log --show-signature` shows `BAD signature` | Private key does not match the configured public key | Run `git config user.signingKey` and compare with the registered Signing Key on GitHub |
| GitHub shows `Unverified` | `user.email` in git config does not match a GitHub account with the Signing Key registered | `git config --global user.email your@email.com` (must match GitHub account email) |
| `nix develop` shellHook does nothing on macOS | Shell started outside a git repository | `cd` to the repository root before running `nix develop` |
| Signing key path changes after re-keying | `~/.gitconfig` retains the old key path | Re-run `configure-git-signing.sh` or set: `git config --global user.signingKey ~/.ssh/id_ed25519.pub` |
