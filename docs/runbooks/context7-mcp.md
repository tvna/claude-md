# context7 MCP server runbook

> Operator procedure for the context7 MCP server declared in
> [`apm.yml`](../../apm.yml). It exists because primary-source lookups are a
> Principle 2 requirement (ground claims in authoritative docs or observed
> state), and context7 makes those lookups quicker to reach. Refs #1188, #1190.

## What context7 is

[context7](https://github.com/upstash/context7) is an MCP server that pulls
up-to-date, version-specific library documentation into the agent's context.
It is a primary-source accelerator for the Principle 2 rule "ground claims
about how an external tool, library, API, or platform behaves in primary
sources".

## How it is declared here

This repository is the master that distributes `CLAUDE.md` / `AGENTS.md` /
skills to downstream projects, so it declares context7 only -- it does not
wire any client config of its own. The declaration in `apm.yml` is:

```yaml
dependencies:
  mcp:
  - name: context7
    transport: http
    url: https://mcp.context7.com/mcp
```

- `transport: http` with an explicit `url` is a self-defined entry, so it does
  not depend on resolving the server against a registry at compile time.
- `apm compile` does not consume the `mcp` block; it only regenerates
  `CLAUDE.md` / `AGENTS.md` from `.apm/instructions/`. The `mcp` block is read
  by `apm install` (see below).

## Keyless default

context7 works without an API key at a lower rate limit. Nothing in this
repository requires a key, and no key is committed. For most documentation
lookups the keyless tier is sufficient.

## Optional API key (issuance and storage)

A free API key raises the rate limit. When a downstream project wants one:

- **Where to issue**: create a free key at `context7.com/dashboard`.
- **Minimum scope**: documentation retrieval only.
- **Where to store**: in the consuming client's environment or secret store,
  passed as the `CONTEXT7_API_KEY` HTTP header. **Never** place the key in
  `apm.yml`, in any committed file, or in logs / PR bodies / issue comments
  (Principle 4: secrets never reach an output sink).
- **Rotation**: re-issue from the dashboard; revoke the old key there.
- **Verification**: confirm an authenticated documentation request returns
  HTTP 200 without printing the key value.

## Downstream wiring

MCP server support landed in apm v0.12.0 (this repository pins
`apm-cli==0.12.1`). A downstream project that has pulled this master in wires
context7 into its own clients with:

```bash
apm install --mcp context7
```

`apm install` writes the MCP entry into each detected client config (for
Claude Code: project-scope `.mcp.json` and user-scope `~/.claude.json`).
Downstream consumers still own that wiring for their own clients.

### Master-repo `.mcp.json` generation

The master repository now renders its *own* project-scope `.mcp.json` so a
Claude Code session opened against this repo can reach context7 without the
operator running `apm install` by hand. This supersedes the earlier stance
("the master repository deliberately does not run this step").

- **Source of truth:** the `dependencies.mcp` block in `apm.yml`.
- **Renderer:** `scripts/gen_mcp_json.py` reads `apm.yml` and writes
  `.mcp.json` offline and idempotently. It does *not* call `apm install`,
  reach the MCP endpoint, or touch user-scope `~/.claude.json` -- it renders
  only the project-scope file from the in-repo declaration.
- **Trigger:** the `SessionStart` hook chain in `.claude/settings.json`
  (`uv run python3 scripts/gen_mcp_json.py`), so generation is guaranteed
  every session rather than relying on operator memory.
- **Not committed:** `.mcp.json` is a rendered build artefact and can carry
  per-client credentials, so it stays git-ignored
  (`docs/standards/repo-scope.md`). The secret rule above still holds -- the
  renderer never bakes a key into the file; an authenticated server supplies
  its key via the runtime `env` indirection.
- **Drift check:** `scripts/gen_mcp_json.py --check` exits non-zero when the
  on-disk `.mcp.json` no longer matches a fresh render of `apm.yml`.

## Verification

- `apm.yml` parses and the entry is present:

  ```bash
  uv run --with 'apm-cli==0.12.1' apm compile
  ```

  exits 0 (the `mcp` block does not change `CLAUDE.md` / `AGENTS.md`, but a
  malformed entry would fail the parse).
- Flag reference for the downstream install command: `apm install --help`
  (consult the [apm MCP servers guide](https://microsoft.github.io/apm/guides/mcp-servers/)
  as the primary source).

## See also

- [`apm.yml`](../../apm.yml) -- the declaration of record.
- [`README.md`](../../README.md) -- "Using This From Another Project".
- [`docs/runbooks/agent-provenance.md`](agent-provenance.md) -- provenance
  review criteria for MCP servers and other agent extensions.
