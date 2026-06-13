# README Authoring Standard

Tracking issue: [#1094](https://github.com/tvna/claude-md/issues/1094)

This is the adopted contract for the structure of the repository's
top-level READMEs (`README.md`, `README.ja.md`, `README.zh.md`). It exists
so a reviewer can decide, by inspection, whether a README change keeps the
document coherent: whether a new line lands in the right section, whether a
tool-specific note breaks the reader's flow, and whether the three language
copies still move together.

It records prose rules rather than a new CI gate. Required-heading checking
is the deferred check in
[`documentation-quality.md`](./documentation-quality.md); until that gate
lands for READMEs, this document is the authoritative reference a reviewer
applies by hand. The link and inventory gates already cover these files
(see [Link discipline](#link-discipline)).

## Scope

This standard governs the three top-level READMEs:

- `README.md` (English, canonical)
- `README.ja.md` (Japanese)
- `README.zh.md` (Simplified Chinese)

It does not govern lane README files under `docs/` (`docs/standards/README.md`
and siblings); their placement rules live in
[`docs/INDEX.md`](../INDEX.md) and each lane README itself.

## Canonical section order

`README.md` is the canonical copy; the translations mirror its heading
structure one-to-one. The adopted top-level order is:

1. `# <title>` plus the badges row, the language switcher line, and a
   single-sentence statement of what the repository is.
2. `## Purpose` - why the repository exists and what does not belong in it.
3. `## The Six Principles` - the principle summary table linking the
   compiled `CLAUDE.md` / `AGENTS.md`.
4. `## Building` - how to compile the instructions from source.
5. `## Using This From Another Project` - the consumer-facing integration
   steps (see the next section for its internal shape).
6. `## Change Policy` - the rules for editing this repository, ending with
   the pointer to [`docs/INDEX.md`](../INDEX.md).

Add a new top-level section only when its content fits none of the above.
When in doubt, extend an existing section rather than introducing a new
`##` heading; this keeps the reader's mental table of contents stable
across the three languages.

## Numbered steps vs tool-specific notes

This is the core rule and the reason this standard exists.

- **Numbered `###` headings (`### 1.`, `### 2.`, ...) are for ordered
  steps only** - a sequence the reader performs in order. Inside
  `## Using This From Another Project` the steps are: add the sync
  workflow, add project-specific rules, pull in updates.
- **Tool-specific notes do not belong between numbered steps.** A note that
  applies only to one downstream tool (Codex, Devin, and future targets) is
  not a step in the sequence; inserting it as `### <Tool>` between `### 1.`
  and `### 2.` breaks the numbering and reads as an abrupt interruption.
- **Collect tool-specific notes in a single unnumbered `### Tool-specific
  notes` subsection placed after the last numbered step.** Each note is a
  bullet that names the tool in bold and links to the adopted contract that
  backs it, so the mention carries its own context instead of appearing
  without explanation. For example, the Devin note links to
  [`devin-apm-compatibility.md`](./devin-apm-compatibility.md).

The translations use the localized equivalent of `### Tool-specific notes`
as their heading; the Japanese and Chinese READMEs carry that heading in
their own language so the three files still match one-to-one.

## Multi-language sync

The three READMEs are a trio that moves together. A substantive change to
`README.md` must land with the equivalent change to `README.ja.md` and
`README.zh.md` in the same PR. This is enforced by the deterministic gate
documented in
[`docs/runbooks/readme-translation-drift.md`](../runbooks/readme-translation-drift.md)
(`scripts/verify_readme_translation.py`).

- Keep headings in one-to-one correspondence across the three files; the
  matching position is then obvious when adding a translated line.
- The opt-out marker `<!-- readme-translation-ack -->` is for genuinely
  English-only edits (a typo, a renderer fix). A new section, bullet, or
  code block is substantive and must ship with translations - do not use
  the marker to defer translation of new content.

## Link discipline

Relative links in any README must resolve inside the repository, and
heading fragments must resolve to a real anchor. This is enforced by the
D1 gate in [`documentation-quality.md`](./documentation-quality.md)
(`scripts/scan_markdown_links.py`). When a README points at an adopted
contract - as the tool-specific notes do - prefer a repository-relative
link such as `./docs/standards/<file>.md` so the gate can verify it.

## Rationale (CLAUDE.md mapping)

| Rule | CLAUDE.md anchor | What it enforces |
|---|---|---|
| Numbered headings for ordered steps only; tool notes collected after them | Principle 6 | A reader detects the document's shape by inspection; a tool note no longer interrupts the step sequence. |
| Each tool note links to its adopted contract | Principle 6 | The mention carries its own context; the reader is not left guessing why a tool appears. |
| Extend an existing section before adding a new one | Principle 4 | Minimum structure; prefer removing or folding over adding headings. |
| Translations move with the canonical copy | Principle 3 | Parity is harness-enforced, not operator-remembered. |

## Verification

For a README or this-standard change, run:

```sh
python3 scripts/scan_markdown_links.py verify
python3 scripts/scan_docs_inventory.py verify
python3 scripts/verify_readme_translation.py verify \
  --base-ref origin/main --body-file /dev/null
```

This document must stay ASCII-only:

```sh
python3 -c "import pathlib; \
  assert pathlib.Path('docs/standards/readme-authoring-standard.md').read_text().isascii()"
```

## References

- [`documentation-quality.md`](./documentation-quality.md) - the D1 link
  gate and D2 inventory gate that cover these files.
- [`docs/runbooks/readme-translation-drift.md`](../runbooks/readme-translation-drift.md) -
  the translation-parity gate and opt-out procedure.
- [`devin-apm-compatibility.md`](./devin-apm-compatibility.md) - the adopted
  Devin contract the README tool note links to.
- [`docs/INDEX.md`](../INDEX.md) - the docs inventory this standard is
  registered in.
- [CLAUDE.md](../../CLAUDE.md) - principles 3, 4, 6 (rationale tie-in).
