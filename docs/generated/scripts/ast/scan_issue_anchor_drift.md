# AST graph: scripts/scan_issue_anchor_drift.py

This file is generated from `scripts/scan_issue_anchor_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _check_config(...)

```mermaid
flowchart TD
    N001["_check_config(...)"]
    N002["try"]
    N003["load_anchors(...)"]
    N004["except (ValueError, OSError, tomllib.TOMLDecodeError)"]
    N005["return [f'<str>{_rel(config_path, repo_root)}<str>{error}']"]
    N006["errors = []"]
    N007["data = loads(...)"]
    N008["for entry in data['<str>']:     for consumer in entry['<str>']:         if not (repo_root / consumer).exists():             errors.append(f'<str>{_rel(config_path, repo_root)}<str>{entry['<str>']!r}<str>{consumer!r}<str>')"]
    N009["return errors"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _check_workflows(...)

```mermaid
flowchart TD
    N001["_check_workflows(...)"]
    N002["errors = []"]
    N003["for workflow in sorted((repo_root / '<str>' / '<str>').glob('<str>')):     for lineno, line in enumerate(workflow.read_text(encoding='<str>').splitlines(), start=1):         if line.lstrip().startswith('<str>'):             continue         for pattern, hint in _WORKFLOW_PATTERNS:             if pattern.search(line):                 errors.append(f'<str>{_rel(workflow, repo_root)}<str>{lineno}<str>{line.strip()!r}<str>{hint}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _check_templates(...)

```mermaid
flowchart TD
    N001["_check_templates(...)"]
    N002["errors = []"]
    N003["templates_dir = repo_root / '<str>' / '<str>'"]
    N004["if not templates_dir.is_dir()"]
    N005["return errors"]
    N006["for template in sorted(templates_dir.glob('<str>')):     for lineno, line in enumerate(template.read_text(encoding='<str>').splitlines(), start=1):         if _TEMPLATE_PATTERN.search(line):             errors.append(f'<str>{_rel(template, repo_root)}<str>{lineno}<str>{line.strip()!r}<str>')"]
    N007["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## _check_script_constants(...)

```mermaid
flowchart TD
    N001["_check_script_constants(...)"]
    N002["errors = []"]
    N003["for script in sorted((repo_root / '<str>').glob('<str>')):     tree = ast.parse(script.read_text(encoding='<str>'))     for node in tree.body:         targets: list[ast.expr]         if isinstance(node, ast.Assign):             targets, value = (node.targets, node.value)         elif isinstance(node, ast.AnnAssign) and node.value is not None:             targets, value = ([node.target], node.value)         else:             continue         if not (isinstance(value, ast.Constant) and isinstance(value.value, int) and (not isinstance(value.value, bool))):             continue         for target in targets:             if isinstance(target, ast.Name) and '<str>' in target.id and target.id.isupper():                 errors.append(f'<str>{_rel(script, repo_root)}<str>{node.lineno}<str>{target.id}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _rel(...)

```mermaid
flowchart TD
    N001["_rel(...)"]
    N002["try"]
    N003["return str(path.relative_to(repo_root))"]
    N004["except ValueError"]
    N005["return str(path)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["errors = [*_check_config(repo_root, config_path), *_check_workflows(repo_root), *_check_templates(repo_root), *_check_script_constants(repo_root)]"]
    N003["for error in errors:     print(error, file=sys.stderr)"]
    N004["if errors"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["args = parse_args(...)"]
    N008["repo_root = Path(...)"]
    N009["config_path = Path(args.config) if args.config else repo_root / '<str>' / '<str>'"]
    N010["try"]
    N011["return verify(repo_root, config_path)"]
    N012["except (OSError, SyntaxError, ValueError, KeyError, TypeError)"]
    N013["print(...)"]
    N014["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
```
