# AST graph: scripts/scan_area_path_coverage.py

This file is generated from `scripts/scan_area_path_coverage.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _run_git(...)

```mermaid
flowchart TD
    N001["_run_git(...)"]
    N002["completed = run_git(...)"]
    N003["if completed.returncode != 0"]
    N004["detail = strip(...)"]
    N005["raise RuntimeError(f\"<str>{'<str>'.join(args)}<str>{detail}\")"]
    N006["return completed.stdout"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## load_policy(...)

```mermaid
flowchart TD
    N001["load_policy(...)"]
    N002["with path.open('<str>') as handle:
    return tomllib.load(handle)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## declared_area_labels(...)

```mermaid
flowchart TD
    N001["declared_area_labels(...)"]
    N002["labels = get(...)"]
    N003["return {str(label['<str>']) for label in labels if isinstance(label, dict) and label.get('<str>') == '<str>' and ('<str>' in label)}"]
    N001 -->|"start"| N002
    N002 --> N003
```

## area_path_entries(...)

```mermaid
flowchart TD
    N001["area_path_entries(...)"]
    N002["return [entry for entry in policy.get('<str>', []) if isinstance(entry, dict)]"]
    N001 -->|"start"| N002
```

## mapped_areas(...)

```mermaid
flowchart TD
    N001["mapped_areas(...)"]
    N002["return {str(entry['<str>']) for entry in area_path_entries(policy) if isinstance(entry.get('<str>'), str)}"]
    N001 -->|"start"| N002
```

## glob_top_levels(...)

```mermaid
flowchart TD
    N001["glob_top_levels(...)"]
    N002["tops = set(...)"]
    N003["for entry in area_path_entries(policy):
    for raw in entry.get('<str>', []):
        if isinstance(raw, str) and raw:
            tops.add(PurePosixPath(raw).parts[0])"]
    N004["return tops"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## tracked_top_level_dirs(...)

```mermaid
flowchart TD
    N001["tracked_top_level_dirs(...)"]
    N002["output = runner(...)"]
    N003["return {line.strip() for line in output.splitlines() if line.strip()}"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _err(...)

```mermaid
flowchart TD
    N001["_err(...)"]
    N002["return f'<str>{POLICY_PATH.as_posix()}<str>{message}'"]
    N001 -->|"start"| N002
```

## verify_policy(...)

```mermaid
flowchart TD
    N001["verify_policy(...)"]
    N002["errors = []"]
    N003["declared = declared_area_labels(...)"]
    N004["mapped = mapped_areas(...)"]
    N005["for entry in area_path_entries(policy):
    area = entry.get('<str>')
    if not isinstance(area, str) or not area:
        errors.append(_err('<str>'))
        continue
    paths = entry.get('<str>')
    if not isinstance(paths, list) or not paths:
        errors.append(_err(f'<str>{area}<str>'))"]
    N006["for area in sorted(mapped - declared):
    errors.append(_err(f'<str>{area}<str>'))"]
    N007["for area in sorted(declared - mapped):
    errors.append(_err(f'<str>{area}<str>'))"]
    N008["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## verify_directory_coverage(...)

```mermaid
flowchart TD
    N001["verify_directory_coverage(...)"]
    N002["covered = glob_top_levels(...)"]
    N003["errors = []"]
    N004["for directory in sorted(tracked_top_level_dirs(root, runner)):
    if directory not in covered:
        errors.append(_err(f'<str>{directory}<str>'))"]
    N005["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["policy_file = root / POLICY_PATH"]
    N004["if not policy_file.exists()"]
    N005["return [_err(f'<str>{POLICY_PATH.as_posix()}<str>')]"]
    N006["policy = load_policy(...)"]
    N007["return verify_policy(policy) + verify_directory_coverage(policy, root, runner)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["args = parse_args(...)"]
    N006["if args.command == 'verify'"]
    N007["errors = verify(...)"]
    N008["for error in errors:
    print(error, file=sys.stderr)"]
    N009["return 1 if errors else 0"]
    N010["error(...)"]
    N011["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N010 --> N011
```
