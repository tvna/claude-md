# AST graph: scripts/scan_ssot_drift.py

This file is generated from `scripts/scan_ssot_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## workflow_targets_pull_request(...)

```mermaid
flowchart TD
    N001["workflow_targets_pull_request(...)"]
    N002["in_on_block = False"]
    N003["on_block_indent = -1"]
    N004["for raw_line in yaml_text.splitlines():     stripped = raw_line.lstrip()     indent = len(raw_line) - len(stripped)     if not stripped or stripped.startswith('<str>'):         continue     if not in_on_block:         if stripped.startswith('<str>'):             tail = stripped[3:].strip()             if tail.startswith('<str>') and '<str>' in tail:                 tokens = re.findall('<str>', tail)                 if '<str>' in tokens:                     return True             in_on_block = True             on_block_indent = indent         continue     if indent <= on_block_indent:         return False     head = stripped.split('<str>', 1)[0]     if head == '<str>':         return True"]
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

## diff_steps_vs_workflows(...)

```mermaid
flowchart TD
    N001["diff_steps_vs_workflows(...)"]
    N002["ci_scripts = {ref.script for ref in workflow_refs}"]
    N003["missing = [ref for ref in workflow_refs if ref.script not in declared and ref.script not in excluded]"]
    N004["extra = frozenset(declared) - ci_scripts"]
    N005["return (missing, extra)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _as_list(...)

```mermaid
flowchart TD
    N001["_as_list(...)"]
    N002["return value if isinstance(value, list) else []"]
    N001 -->|"start"| N002
```

## _as_dict(...)

```mermaid
flowchart TD
    N001["_as_dict(...)"]
    N002["return value if isinstance(value, dict) else {}"]
    N001 -->|"start"| N002
```

## pretooluse_manifest(...)

```mermaid
flowchart TD
    N001["pretooluse_manifest(...)"]
    N002["names = set(...)"]
    N003["for target in _as_list(_as_dict(agent_hooks).get('<str>')):     target_d = _as_dict(target)     hooks = _as_dict(_as_dict(target_d.get('<str>')).get('<str>'))     for group in _as_list(hooks.get('<str>')):         for hook in _as_list(_as_dict(group).get('<str>')):             command = _as_dict(hook).get('<str>')             if isinstance(command, str):                 names.update(_SCRIPT_REF.findall(command))"]
    N004["return frozenset(names)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## steps_manifest(...)

```mermaid
flowchart TD
    N001["steps_manifest(...)"]
    N002["scripts = set(...)"]
    N003["unmapped = set(...)"]
    N004["for step in steps:     matched = {m.group(1) for token in step.argv if (m := _SCRIPT_REF.search(token))}     if matched:         scripts.update(matched)     elif step.name not in STEPS_NO_SCRIPT_ALLOWLIST:         unmapped.add(step.name)"]
    N005["return (frozenset(scripts), frozenset(unmapped))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## pre_commit_manifest(...)

```mermaid
flowchart TD
    N001["pre_commit_manifest(...)"]
    N002["scripts = set(...)"]
    N003["unmapped = set(...)"]
    N004["repos = _as_list(...)"]
    N005["for repo in repos:     for hook in _as_list(_as_dict(repo).get('<str>')):         hook_d = _as_dict(hook)         hook_id = hook_d.get('<str>')         text = str(hook_d.get('<str>', '<str>')) + '<str>' + '<str>'.join((str(a) for a in _as_list(hook_d.get('<str>'))))         found = _SCRIPT_REF.findall(text)         if found:             scripts.update(found)         elif isinstance(hook_id, str) and hook_id not in PRE_COMMIT_NO_SCRIPT_ALLOWLIST:             unmapped.add(hook_id)"]
    N006["return (frozenset(scripts), frozenset(unmapped))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _ci_scripts(...)

```mermaid
flowchart TD
    N001["_ci_scripts(...)"]
    N002["return frozenset({ref.script for ref in workflow_refs}) - CI_RUNNER_EXCLUDE"]
    N001 -->|"start"| N002
```

## ci_manifest(...)

```mermaid
flowchart TD
    N001["ci_manifest(...)"]
    N002["return _ci_scripts(collect_workflow_refs(workflows_dir))"]
    N001 -->|"start"| N002
```

## server_native_rules(...)

```mermaid
flowchart TD
    N001["server_native_rules(...)"]
    N002["return frozenset((rule['<str>'] for rule in _as_list(_as_dict(rulesets).get('<str>')) if isinstance(rule, dict) and isinstance(rule.get('<str>'), str)))"]
    N001 -->|"start"| N002
```

## registry_scripts_for_plane(...)

```mermaid
flowchart TD
    N001["registry_scripts_for_plane(...)"]
    N002["result = {}"]
    N003["for gate in _as_list(registry.get('<str>')):     gate_d = _as_dict(gate)     if gate_d.get('<str>') != '<str>':         continue     script = gate_d.get('<str>')     gate_id = gate_d.get('<str>')     planes = _as_list(gate_d.get('<str>'))     if isinstance(script, str) and isinstance(gate_id, str) and (plane in planes):         result[script.removeprefix('<str>').removesuffix('<str>')] = gate_id"]
    N004["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## registry_native_rules_for_plane(...)

```mermaid
flowchart TD
    N001["registry_native_rules_for_plane(...)"]
    N002["result = {}"]
    N003["for gate in _as_list(registry.get('<str>')):     gate_d = _as_dict(gate)     if gate_d.get('<str>') != '<str>':         continue     native_rule = gate_d.get('<str>')     gate_id = gate_d.get('<str>')     planes = _as_list(gate_d.get('<str>'))     if isinstance(native_rule, str) and isinstance(gate_id, str) and (plane in planes):         result[native_rule] = gate_id"]
    N004["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## registry_cluster_planes(...)

```mermaid
flowchart TD
    N001["registry_cluster_planes(...)"]
    N002["result = {}"]
    N003["for gate in _as_list(registry.get('<str>')):     gate_d = _as_dict(gate)     cluster = gate_d.get('<str>')     if isinstance(cluster, str):         result.setdefault(cluster, set()).update((p for p in _as_list(gate_d.get('<str>')) if isinstance(p, str)))"]
    N004["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## registry_ci_only_scripts(...)

```mermaid
flowchart TD
    N001["registry_ci_only_scripts(...)"]
    N002["result = set(...)"]
    N003["for gate in _as_list(registry.get('<str>')):     gate_d = _as_dict(gate)     if gate_d.get('<str>') != '<str>':         continue     script = gate_d.get('<str>')     planes = _as_list(gate_d.get('<str>'))     if isinstance(script, str) and '<str>' in planes and ('<str>' not in planes):         result.add(script.removeprefix('<str>').removesuffix('<str>'))"]
    N004["return frozenset(result)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## diff_plane(...)

```mermaid
flowchart TD
    N001["diff_plane(...)"]
    N002["warnings = []"]
    N003["for script in sorted(manifest_scripts - registry_scripts.keys()):     warnings.append(f'{manifest_label}<str>{script}<str>{plane}<str>')"]
    N004["for script in sorted(registry_scripts.keys() - manifest_scripts):     warnings.append(f'<str>{registry_scripts[script]!r}<str>{plane}<str>{script}<str>{manifest_label}<str>')"]
    N005["return warnings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## diff_native(...)

```mermaid
flowchart TD
    N001["diff_native(...)"]
    N002["warnings = []"]
    N003["for rule in sorted(manifest_rules - registry_rules.keys()):     warnings.append(f'{_RULESETS_PATH}<str>{rule!r}<str>')"]
    N004["for rule in sorted(registry_rules.keys() - manifest_rules):     warnings.append(f'<str>{registry_rules[rule]!r}<str>{rule!r}<str>{_RULESETS_PATH}<str>')"]
    N005["return warnings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## diff_clusters(...)

```mermaid
flowchart TD
    N001["diff_clusters(...)"]
    N002["warnings = []"]
    N003["achieved = registry_cluster_planes(...)"]
    N004["for cluster in _as_list(registry.get('<str>')):     cluster_d = _as_dict(cluster)     cluster_id = cluster_d.get('<str>')     if not isinstance(cluster_id, str):         continue     expected = {p for p in _as_list(cluster_d.get('<str>')) if isinstance(p, str)}     missing = expected - achieved.get(cluster_id, set())     for plane in sorted(missing):         warnings.append(f'<str>{cluster_id!r}<str>{plane!r}<str>{cluster_id!r}<str>')"]
    N005["return warnings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## diff_unmapped(...)

```mermaid
flowchart TD
    N001["diff_unmapped(...)"]
    N002["return [f'{manifest_label}<str>{name!r}<str>' for name in sorted(unmapped)]"]
    N001 -->|"start"| N002
```

## verify_registry(...)

```mermaid
flowchart TD
    N001["verify_registry(...)"]
    N002["warnings = []"]
    N003["pretooluse_scripts = pretooluse_manifest(...)"]
    N004["warnings += diff_plane(pretooluse_scripts, registry_scripts_for_plane(registry, '<str>'), manifest_label=_AGENT_HOOKS_PATH, plane='<str>')"]
    N005["warnings += diff_plane(push_scripts, registry_scripts_for_plane(registry, '<str>'), manifest_label='<str>', plane='<str>')"]
    N006["warnings += diff_unmapped(push_unmapped, manifest_label='<str>')"]
    N007["(commit_scripts, commit_unmapped) = pre_commit_manifest(...)"]
    N008["warnings += diff_plane(commit_scripts, registry_scripts_for_plane(registry, '<str>'), manifest_label=_PRE_COMMIT_CONFIG_PATH, plane='<str>')"]
    N009["warnings += diff_unmapped(commit_unmapped, manifest_label=_PRE_COMMIT_CONFIG_PATH)"]
    N010["ci_scripts = _ci_scripts(...)"]
    N011["warnings += diff_plane(ci_scripts, registry_scripts_for_plane(registry, '<str>'), manifest_label='<str>', plane='<str>')"]
    N012["warnings += diff_native(server_native_rules(rulesets), registry_native_rules_for_plane(registry, '<str>'))"]
    N013["warnings += diff_clusters(registry)"]
    N014["blocking = [DriftWarning(message=message) for message in warnings]"]
    N015["excluded = registry_ci_only_scripts(registry) | frozenset(STEPS_VS_WORKFLOW_RESIDUAL_ALLOWLIST) | CI_RUNNER_EXCLUDE"]
    N016["(missing_steps, extra_declared) = diff_steps_vs_workflows(...)"]
    N017["blocking += [DriftWarning(message=f'<str>{ref.script}<str>{ref.workflow!r}<str>', workflow=ref.workflow) for ref in missing_steps]"]
    N018["advisory = [f'<str>{name!r}<str>{name}<str>' for name in sorted(extra_declared)]"]
    N019["return VerifyResult(blocking=blocking, advisory=advisory)"]
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
    N016 --> N017
    N017 --> N018
    N018 --> N019
```

## _load_json(...)

```mermaid
flowchart TD
    N001["_load_json(...)"]
    N002["return json.loads(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
```

## _load_yaml(...)

```mermaid
flowchart TD
    N001["_load_yaml(...)"]
    N002["return yaml.safe_load(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["if argv is None"]
    N003["argv = sys.argv[1:]"]
    N004["command = argv[0] if argv else None"]
    N005["if command != 'verify'"]
    N006["print(...)"]
    N007["return 64"]
    N008["parser = ArgumentParser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["args = parse_args(...)"]
    N016["registry_path = _REPO_ROOT / args.registry"]
    N017["agent_hooks_path = _REPO_ROOT / args.agent_hooks"]
    N018["pre_commit_path = _REPO_ROOT / args.pre_commit_config"]
    N019["rulesets_path = _REPO_ROOT / args.rulesets"]
    N020["workflows_dir = _REPO_ROOT / args.workflows_dir"]
    N021["for label, path in (('<str>', registry_path), ('<str>', agent_hooks_path), ('<str>', pre_commit_path), ('<str>', rulesets_path)):     if not path.exists():         print(f'<str>{_SCRIPT}<str>{label}<str>{path}<str>', file=sys.stderr)         return 1"]
    N022["if not workflows_dir.is_dir()"]
    N023["print(...)"]
    N024["return 1"]
    N025["try"]
    N026["registry = _load_json(...)"]
    N027["agent_hooks = _load_json(...)"]
    N028["pre_commit_config = _load_yaml(...)"]
    N029["rulesets = _load_json(...)"]
    N030["except (OSError, ValueError, yaml.YAMLError)"]
    N031["print(...)"]
    N032["return 1"]
    N033["if not isinstance(registry, dict)"]
    N034["print(...)"]
    N035["return 1"]
    N036["workflow_refs = collect_workflow_refs(...)"]
    N037["(push_scripts, push_unmapped) = steps_manifest(...)"]
    N038["result = verify_registry(...)"]
    N039["for message in result.advisory:     print(f'<str>{_SCRIPT}<str>{message}', file=sys.stderr)"]
    N040["if result.blocking"]
    N041["for warning in result.blocking:     if warning.workflow:         print(f'<str>{warning.workflow}<str>{_SCRIPT}<str>{warning.message}', file=sys.stderr)     else:         print(f'<str>{_SCRIPT}<str>{warning.message}', file=sys.stderr)"]
    N042["print(...)"]
    N043["return 1"]
    N044["print(...)"]
    N045["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 -->|"true"| N023
    N023 --> N024
    N022 -->|"false"| N025
    N025 -->|"try"| N026
    N026 --> N027
    N027 --> N028
    N028 --> N029
    N025 -->|"raises"| N030
    N030 --> N031
    N031 --> N032
    N029 --> N033
    N033 -->|"true"| N034
    N034 --> N035
    N033 -->|"false"| N036
    N036 --> N037
    N037 --> N038
    N038 --> N039
    N039 --> N040
    N040 -->|"true"| N041
    N041 --> N042
    N042 --> N043
    N040 -->|"false"| N044
    N044 --> N045
```
