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

## validate_exemption(...)

```mermaid
flowchart TD
    N001["validate_exemption(...)"]
    N002["if not isinstance(spec, dict)"]
    N003["return f'<str>{name!r}<str>'"]
    N004["agents = get(...)"]
    N005["if not isinstance(agents, list) or not agents or len(set(agents)) != len(agents) or (not set(agents) <= set(AGENTS))"]
    N006["return f'<str>{name!r}<str>{list(AGENTS)}'"]
    N007["if set(agents) == set(AGENTS)"]
    N008["return f'<str>{name!r}<str>'"]
    N009["rationale = get(...)"]
    N010["if not isinstance(rationale, str) or not rationale.strip()"]
    N011["return f'<str>{name!r}<str>'"]
    N012["issue = get(...)"]
    N013["if not isinstance(issue, int) or isinstance(issue, bool)"]
    N014["return f'<str>{name!r}<str>'"]
    N015["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## find_installer_parity_violations(...)

```mermaid
flowchart TD
    N001["find_installer_parity_violations(...)"]
    N002["all_agents = set(...)"]
    N003["universe = set(...)"]
    N004["for names in installers_by_agent.values():     universe |= names"]
    N005["violations = []"]
    N006["for name in sorted(exemptions):     err = validate_exemption(name, exemptions[name])     if err:         violations.append(err)     elif name not in universe:         violations.append(f'<str>{name!r}<str>')"]
    N007["for name in sorted(universe):     actual = {agent for agent in AGENTS if name in installers_by_agent.get(agent, set())}     spec = exemptions.get(name)     if spec is not None and (not validate_exemption(name, spec)):         declared_agents = spec['<str>']         declared = set(declared_agents) if isinstance(declared_agents, list) else set()         if actual != declared:             violations.append(f'<str>{name!r}<str>{sorted(declared)}<str>{sorted(actual)}<str>')         continue     if spec is not None:         continue     if actual != all_agents:         missing = sorted(all_agents - actual)         violations.append(f'<str>{name!r}<str>{sorted(actual)}<str>{missing}<str>')"]
    N008["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["claude_settings = loads(...)"]
    N003["codex_data = loads(...)"]
    N004["devin_data = loads(...)"]
    N005["claude_hooks = collect_claude_hooks(...)"]
    N006["codex_hooks = collect_codex_hooks(...)"]
    N007["missing = find_drift(...)"]
    N008["installers_by_agent = {'<str>': collect_installers(claude_settings), '<str>': collect_installers(codex_data), '<str>': collect_installers(devin_data)}"]
    N009["parity_violations = find_installer_parity_violations(...)"]
    N010["for entry in missing:     print(f'<str>{entry.event}<str>{entry.script}<str>', file=sys.stderr)"]
    N011["for message in parity_violations:     print(f'<str>{message}<str>', file=sys.stderr)"]
    N012["for script, rationale in sorted(ALLOWLIST.items()):     print(f'<str>{script}<str>{rationale}', file=sys.stderr)"]
    N013["for name, spec in sorted(INSTALLER_PARITY_EXEMPTIONS.items()):     exempt_agents = spec.get('<str>')     exempt_rationale = spec.get('<str>')     print(f'<str>{name}<str>{exempt_agents}<str>{exempt_rationale}', file=sys.stderr)"]
    N014["if missing or parity_violations"]
    N015["return 1"]
    N016["return 0"]
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
    N014 -->|"true"| N015
    N014 -->|"false"| N016
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
    N007["add_argument(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```
