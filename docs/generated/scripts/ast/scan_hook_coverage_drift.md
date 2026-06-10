# AST graph: scripts/scan_hook_coverage_drift.py

This file is generated from `scripts/scan_hook_coverage_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _extract_scripts_from_command(...)

```mermaid
flowchart TD
    N001["_extract_scripts_from_command(...)"]
    N002["return _SCRIPT_REF.findall(command)"]
    N001 -->|"start"| N002
```

## _is_superpowers(...)

```mermaid
flowchart TD
    N001["_is_superpowers(...)"]
    N002["return isinstance(group, dict) and group.get('<str>') == '<str>'"]
    N001 -->|"start"| N002
```

## _iter_commands(...)

```mermaid
flowchart TD
    N001["_iter_commands(...)"]
    N002["raw_hooks = get(...)"]
    N003["if not isinstance(raw_hooks, dict)"]
    N004["return"]
    N005["for event in HOOK_EVENTS:     raw_groups = raw_hooks.get(event, [])     if not isinstance(raw_groups, list):         continue     for group in raw_groups:         if not isinstance(group, dict):             continue         if _is_superpowers(group):             continue         handlers = group.get('<str>', [])         if not isinstance(handlers, list):             continue         for handler in handlers:             if not isinstance(handler, dict):                 continue             command = handler.get('<str>', '<str>')             if not isinstance(command, str):                 continue             yield (event, command)"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## _collect_hooks(...)

```mermaid
flowchart TD
    N001["_collect_hooks(...)"]
    N002["result = set(...)"]
    N003["for event, command in _iter_commands(data):     for script in _extract_scripts_from_command(command):         result.add(HookEntry(event=event, script=script))"]
    N004["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## collect_installers(...)

```mermaid
flowchart TD
    N001["collect_installers(...)"]
    N002["result = set(...)"]
    N003["for _event, command in _iter_commands(data):     result.update(_INSTALLER_REF.findall(command))"]
    N004["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## collect_claude_hooks(...)

```mermaid
flowchart TD
    N001["collect_claude_hooks(...)"]
    N002["return _collect_hooks(settings)"]
    N001 -->|"start"| N002
```

## collect_codex_hooks(...)

```mermaid
flowchart TD
    N001["collect_codex_hooks(...)"]
    N002["return _collect_hooks(hooks_data)"]
    N001 -->|"start"| N002
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["codex_pairs = {(h.event, h.script) for h in codex_hooks}"]
    N003["missing = []"]
    N004["for entry in sorted(claude_hooks, key=lambda h: (h.event, h.script)):     if (entry.event, entry.script) not in codex_pairs and entry.script not in allowlist:         missing.append(entry)"]
    N005["return missing"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## find_installer_drift(...)

```mermaid
flowchart TD
    N001["find_installer_drift(...)"]
    N002["drift = []"]
    N003["for name in sorted(claude_installers ^ codex_installers):     if name in exemptions:         continue     if name in claude_installers:         drift.append((name, '<str>', '<str>'))     else:         drift.append((name, '<str>', '<str>'))"]
    N004["return drift"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["claude_path = Path(...)"]
    N003["codex_path = Path(...)"]
    N004["claude_settings = loads(...)"]
    N005["codex_data = loads(...)"]
    N006["claude_hooks = collect_claude_hooks(...)"]
    N007["codex_hooks = collect_codex_hooks(...)"]
    N008["missing = find_drift(...)"]
    N009["claude_installers = collect_installers(...)"]
    N010["codex_installers = collect_installers(...)"]
    N011["installer_drift = find_installer_drift(...)"]
    N012["for entry in missing:     print(f'<str>{entry.event}<str>{entry.script}<str>', file=sys.stderr)"]
    N013["for name, present, absent in installer_drift:     print(f'<str>{name}<str>{present}<str>{absent}<str>', file=sys.stderr)"]
    N014["for script, rationale in sorted(ALLOWLIST.items()):     print(f'<str>{script}<str>{rationale}', file=sys.stderr)"]
    N015["for name, rationale in sorted(INSTALLER_PARITY_EXEMPTIONS.items()):     print(f'<str>{name}<str>{rationale}', file=sys.stderr)"]
    N016["if missing or installer_drift"]
    N017["return 1"]
    N018["return 0"]
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
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
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
