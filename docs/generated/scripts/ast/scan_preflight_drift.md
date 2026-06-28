# AST graph: scripts/scan_preflight_drift.py

This file is generated from `scripts/scan_preflight_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## workflow_targets_pull_request(...)

```mermaid
flowchart TD
    N001["workflow_targets_pull_request(...)"]
    N002["in_on_block = False"]
    N003["on_block_indent = -1"]
    N004["for raw_line in yaml_text.splitlines():     stripped = raw_line.lstrip()     indent = len(raw_line) - len(stripped)     if not stripped or stripped.startswith('<str>'):         continue     if not in_on_block:         if stripped.startswith('<str>'):             tail = stripped[3:].strip()             if tail.startswith('<str>') and '<str>' in tail and ('<str>' not in tail.replace('<str>', '<str>')):                 tokens = re.findall('<str>', tail)                 if '<str>' in tokens:                     return True             in_on_block = True             on_block_indent = indent         continue     if indent <= on_block_indent:         return False     head = stripped.split('<str>', 1)[0]     if head == '<str>':         return True"]
    N005["return False"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## extract_script_refs(...)

```mermaid
flowchart TD
    N001["extract_script_refs(...)"]
    N002["return set(_SCRIPT_REF.findall(yaml_text))"]
    N001 -->|"start"| N002
```

## collect_workflow_refs(...)

```mermaid
flowchart TD
    N001["collect_workflow_refs(...)"]
    N002["refs = []"]
    N003["for path in sorted(workflows_dir.glob('<str>')):     text = path.read_text(encoding='<str>')     if not workflow_targets_pull_request(text):         continue     for script in sorted(extract_script_refs(text)):         refs.append(WorkflowReference(workflow=path.name, script=script))"]
    N004["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## load_preflight_manifest(...)

```mermaid
flowchart TD
    N001["load_preflight_manifest(...)"]
    N002["completed = run(...)"]
    N003["manifest = loads(...)"]
    N004["declared = set(...)"]
    N005["for entry in manifest:     for token in entry.get('<str>', []):         match = _SCRIPT_REF.search(token)         if match:             declared.add(match.group(1))"]
    N006["return declared"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## diff(...)

```mermaid
flowchart TD
    N001["diff(...)"]
    N002["ci_scripts = {ref.script for ref in workflow_refs}"]
    N003["missing = [ref for ref in workflow_refs if ref.script not in declared and ref.script not in allowlist]"]
    N004["extra = declared - ci_scripts"]
    N005["return (missing, extra)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["workflows_dir = Path(...)"]
    N003["preflight = Path(...)"]
    N004["workflow_refs = collect_workflow_refs(...)"]
    N005["declared = load_preflight_manifest(...)"]
    N006["(missing, extra) = diff(...)"]
    N007["for ref in missing:     print(f'<str>{ref.workflow}<str>{ref.script}<str>{ref.workflow}<str>', file=sys.stderr)"]
    N008["for name in sorted(extra):     print(f'<str>{name}<str>{name}<str>', file=sys.stderr)"]
    N009["if missing"]
    N010["return 1"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```
