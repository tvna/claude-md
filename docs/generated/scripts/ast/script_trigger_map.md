# AST graph: scripts/script_trigger_map.py

This file is generated from `scripts/script_trigger_map.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## script_filenames(...)

```mermaid
flowchart TD
    N001["script_filenames(...)"]
    N002["scripts_dir = root / SCRIPTS_DIR"]
    N003["if not scripts_dir.is_dir()"]
    N004["return frozenset()"]
    N005["return frozenset((path.name for path in scripts_dir.glob('<str>') if path.is_file()))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _workflow_refs(...)

```mermaid
flowchart TD
    N001["_workflow_refs(...)"]
    N002["wf_dir = root / WORKFLOWS_DIR"]
    N003["if not wf_dir.is_dir()"]
    N004["return []"]
    N005["refs = []"]
    N006["for path in sorted(wf_dir.glob('<str>')):
    raw = path.read_text(encoding='<str>')
    try:
        document: object = yaml.safe_load(raw)
    except yaml.YAMLError:
        document = None
    jobs = document.get('<str>') if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        for match in _SCRIPT_REF.finditer(raw):
            refs.append(TriggerRef(match.group(1), '<str>', f'{path.name}<str>'))
        continue
    for job_name, job in jobs.items():
        steps = job.get('<str>') if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for step in steps:
            run = step.get('<str>') if isinstance(step, dict) else None
            if not isinstance(run, str):
                continue
            for match in _SCRIPT_REF.finditer(run):
                refs.append(TriggerRef(match.group(1), '<str>', f'{path.name}<str>{job_name}<str>'))"]
    N007["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _precommit_refs(...)

```mermaid
flowchart TD
    N001["_precommit_refs(...)"]
    N002["path = root / PRECOMMIT_CONFIG"]
    N003["if not path.is_file()"]
    N004["return []"]
    N005["document = safe_load(...)"]
    N006["repos = document.get('<str>') if isinstance(document, dict) else None"]
    N007["if not isinstance(repos, list)"]
    N008["return []"]
    N009["refs = []"]
    N010["for repo in repos:
    hooks = repo.get('<str>') if isinstance(repo, dict) else None
    if not isinstance(hooks, list):
        continue
    for hook in hooks:
        entry = hook.get('<str>') if isinstance(hook, dict) else None
        if not isinstance(entry, str):
            continue
        hook_id = str(hook.get('<str>', '<str>'))
        for match in _SCRIPT_REF.finditer(entry):
            refs.append(TriggerRef(match.group(1), '<str>', hook_id))"]
    N011["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
```

## _str_constants(...)

```mermaid
flowchart TD
    N001["_str_constants(...)"]
    N002["return [sub.value for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str)]"]
    N001 -->|"start"| N002
```

## _step_name(...)

```mermaid
flowchart TD
    N001["_step_name(...)"]
    N002["for keyword in call.keywords:
    if keyword.arg == '<str>' and isinstance(keyword.value, ast.Constant):
        value = keyword.value.value
        if isinstance(value, str):
            return value"]
    N003["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _preflight_refs(...)

```mermaid
flowchart TD
    N001["_preflight_refs(...)"]
    N002["path = root / PREFLIGHT_SCRIPT"]
    N003["if not path.is_file()"]
    N004["return []"]
    N005["tree = parse(...)"]
    N006["refs = []"]
    N007["for node in ast.walk(tree):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        continue
    if node.func.id != '<str>':
        continue
    name = _step_name(node)
    argv = next((kw.value for kw in node.keywords if kw.arg == '<str>'), None)
    if argv is None:
        continue
    for literal in _str_constants(argv):
        for match in _SCRIPT_REF.finditer(literal):
            refs.append(TriggerRef(match.group(1), '<str>', name))"]
    N008["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## _agent_hook_refs(...)

```mermaid
flowchart TD
    N001["_agent_hook_refs(...)"]
    N002["path = root / AGENT_HOOKS_SOURCE"]
    N003["if not path.is_file()"]
    N004["return []"]
    N005["data = loads(...)"]
    N006["targets = data.get('<str>') if isinstance(data, dict) else None"]
    N007["if not isinstance(targets, list)"]
    N008["return []"]
    N009["refs = []"]
    N010["for target in targets:
    config = target.get('<str>') if isinstance(target, dict) else None
    hooks = config.get('<str>') if isinstance(config, dict) else None
    if not isinstance(hooks, dict):
        continue
    agent = str(target.get('<str>', '<str>'))
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            inner = entry.get('<str>') if isinstance(entry, dict) else None
            if not isinstance(inner, list):
                continue
            for hook in inner:
                command = hook.get('<str>') if isinstance(hook, dict) else None
                if not isinstance(command, str):
                    continue
                for match in _SCRIPT_REF.finditer(command):
                    refs.append(TriggerRef(match.group(1), '<str>', f'{agent}<str>{event}'))"]
    N011["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
```

## collect_refs(...)

```mermaid
flowchart TD
    N001["collect_refs(...)"]
    N002["refs = set(...)"]
    N003["update(...)"]
    N004["update(...)"]
    N005["update(...)"]
    N006["update(...)"]
    N007["return tuple(sorted(refs))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## unreferenced_scripts(...)

```mermaid
flowchart TD
    N001["unreferenced_scripts(...)"]
    N002["referenced = frozenset(...)"]
    N003["return tuple(sorted(scripts - referenced))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## render_trigger_markdown(...)

```mermaid
flowchart TD
    N001["render_trigger_markdown(...)"]
    N002["lines = ['<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>']"]
    N003["extend(...)"]
    N004["if not refs"]
    N005["extend(...)"]
    N006["extend(...)"]
    N007["for ref in refs:
    lines.append(f'<str>{ref.script}<str>{ref.kind}<str>{ref.location}<str>')"]
    N008["append(...)"]
    N009["unreferenced = unreferenced_scripts(...)"]
    N010["extend(...)"]
    N011["if not unreferenced"]
    N012["extend(...)"]
    N013["append(...)"]
    N014["append(...)"]
    N015["append(...)"]
    N016["append(...)"]
    N017["return '<str>'.join(lines).rstrip() + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N005 --> N009
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N012 --> N017
    N016 --> N017
```

## build_document(...)

```mermaid
flowchart TD
    N001["build_document(...)"]
    N002["return render_trigger_markdown(collect_refs(root), script_filenames(root))"]
    N001 -->|"start"| N002
```

## write_trigger_doc(...)

```mermaid
flowchart TD
    N001["write_trigger_doc(...)"]
    N002["target = root / DOC_PATH"]
    N003["mkdir(...)"]
    N004["write_text(...)"]
    N005["return target"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _cmd_all_doc(...)

```mermaid
flowchart TD
    N001["_cmd_all_doc(...)"]
    N002["write_trigger_doc(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_preview(...)

```mermaid
flowchart TD
    N001["_cmd_preview(...)"]
    N002["write(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_all_doc = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_preview = add_parser(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```
