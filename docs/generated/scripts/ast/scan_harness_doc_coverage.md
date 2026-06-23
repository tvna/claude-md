# AST graph: scripts/scan_harness_doc_coverage.py

This file is generated from `scripts/scan_harness_doc_coverage.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_entries(...)

```mermaid
flowchart TD
    N001["load_entries(...)"]
    N002["with policy_path.open('<str>') as fh:     data = tomllib.load(fh)"]
    N003["return [e for e in data.get('<str>', []) if isinstance(e, dict)]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## is_specifically_covered(...)

```mermaid
flowchart TD
    N001["is_specifically_covered(...)"]
    N002["for entry in entries:     if entry.get('<str>'):         continue     for pattern in entry.get('<str>', []):         if isinstance(pattern, str) and fnmatch.fnmatch(rel_path, pattern):             return True"]
    N003["return False"]
    N001 -->|"start"| N002
    N002 --> N003
```

## collect_scripts(...)

```mermaid
flowchart TD
    N001["collect_scripts(...)"]
    N002["return sorted((p for p in scripts_dir.glob('<str>') if not p.name.startswith('<str>')))"]
    N001 -->|"start"| N002
```

## collect_workflows(...)

```mermaid
flowchart TD
    N001["collect_workflows(...)"]
    N002["return sorted(workflows_dir.glob('<str>')) + sorted(workflows_dir.glob('<str>'))"]
    N001 -->|"start"| N002
```

## _err(...)

```mermaid
flowchart TD
    N001["_err(...)"]
    N002["return f'<str>{rel_path}<str>{_SCRIPT}<str>{message}'"]
    N001 -->|"start"| N002
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["if policy_path is None"]
    N004["policy_path = root / POLICY_PATH"]
    N005["if scripts_dir is None"]
    N006["scripts_dir = root / SCRIPTS_DIR"]
    N007["if workflows_dir is None"]
    N008["workflows_dir = root / WORKFLOWS_DIR"]
    N009["if not policy_path.exists()"]
    N010["print(...)"]
    N011["return []"]
    N012["entries = load_entries(...)"]
    N013["errors = []"]
    N014["files_to_check = []"]
    N015["if scripts_dir.exists()"]
    N016["extend(...)"]
    N017["if workflows_dir.exists()"]
    N018["extend(...)"]
    N019["covered_allowlisted = set(...)"]
    N020["for fpath in files_to_check:     rel = fpath.relative_to(root).as_posix()     specifically_covered = is_specifically_covered(rel, entries)     if specifically_covered:         if rel in COVERAGE_ALLOWLIST:             covered_allowlisted.add(rel)     elif rel in COVERAGE_ALLOWLIST:         pass     else:         errors.append(_err(rel, f'{rel!r}<str>{POLICY_PATH}<str>'))"]
    N021["all_rel = {f.relative_to(root).as_posix() for f in files_to_check}"]
    N022["for allowlisted_path in COVERAGE_ALLOWLIST:     if allowlisted_path in covered_allowlisted:         errors.append(_err(allowlisted_path, f'{allowlisted_path!r}<str>'))     elif allowlisted_path not in all_rel:         errors.append(_err(allowlisted_path, f'{allowlisted_path!r}<str>'))"]
    N023["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["sub = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["args = parse_args(...)"]
    N009["if args.command == 'verify'"]
    N010["policy = Path(args.policy) if args.policy else None"]
    N011["scripts = Path(args.scripts_dir) if args.scripts_dir else None"]
    N012["workflows = Path(args.workflows_dir) if args.workflows_dir else None"]
    N013["errors = verify(...)"]
    N014["for error in errors:     print(error, file=sys.stderr)"]
    N015["if errors"]
    N016["return 1"]
    N017["print(...)"]
    N018["return 0"]
    N019["error(...)"]
    N020["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N009 -->|"false"| N019
    N019 --> N020
```
