# AST graph: scripts/measure_tool_overlap.py

This file is generated from `scripts/measure_tool_overlap.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_zizmor(...)

```mermaid
flowchart TD
    N001["parse_zizmor(...)"]
    N002["data = json.loads(stdout) if stdout.strip() else []"]
    N003["findings = []"]
    N004["for entry in data:     rule = str(entry.get('<str>', '<str>'))     for loc in entry.get('<str>', []):         local = loc.get('<str>', {}).get('<str>', {}).get('<str>')         if not local:             continue         path = local.get('<str>')         point = loc.get('<str>', {}).get('<str>', {}).get('<str>', {})         row = point.get('<str>')         if path is None or row is None:             continue         findings.append(Finding(rule_id=rule, path=str(path), line=int(row) + 1))"]
    N005["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## parse_lychee(...)

```mermaid
flowchart TD
    N001["parse_lychee(...)"]
    N002["data = json.loads(stdout) if stdout.strip() else {}"]
    N003["error_map = data.get('<str>') or {}"]
    N004["findings = []"]
    N005["for path, entries in error_map.items():     for entry in entries:         line = (entry.get('<str>') or {}).get('<str>')         findings.append(Finding(rule_id='<str>', path=str(path), line=int(line or 0)))"]
    N006["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## parse_betterleaks(...)

```mermaid
flowchart TD
    N001["parse_betterleaks(...)"]
    N002["data = json.loads(stdout) if stdout.strip() else None"]
    N003["findings = []"]
    N004["for entry in data or []:     rule = str(entry.get('<str>', '<str>'))     path = _relativize(str(entry.get('<str>', '<str>')), repo_root)     line = int(entry.get('<str>', 0))     findings.append(Finding(rule_id=rule, path=path, line=line))"]
    N005["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _relativize(...)

```mermaid
flowchart TD
    N001["_relativize(...)"]
    N002["candidate = Path(...)"]
    N003["try"]
    N004["return candidate.resolve().relative_to(repo_root.resolve()).as_posix()"]
    N005["except ValueError"]
    N006["return candidate.as_posix()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
```

## diff_findings(...)

```mermaid
flowchart TD
    N001["diff_findings(...)"]
    N002["new_keys = {(f.path, f.line) for f in new_tool}"]
    N003["gate_keys = {(f.path, f.line) for f in gate}"]
    N004["return (new_keys & gate_keys, new_keys - gate_keys, gate_keys - new_keys)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_record(...)

```mermaid
flowchart TD
    N001["build_record(...)"]
    N002["(agree, new_only, gate_only) = diff_findings(...)"]
    N003["return {'<str>': pair_name, '<str>': new_tool, '<str>': existing_gate, '<str>': commit_sha, '<str>': scope_label, '<str>': measured_at_unix_nano, '<str>': recorded_at_unix_nano, '<str>': len(agree) + len(new_only), '<str>': len(agree) + len(gate_only), '<str>': len(agree), '<str>': len(new_only), '<str>': len(gate_only), '<str>': round(new_duration_ms, 3), '<str>': round(gate_duration_ms, 3), '<str>': {'<str>': host_id, '<str>': '<str>'}, '<str>': notes}"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _format_locations(...)

```mermaid
flowchart TD
    N001["_format_locations(...)"]
    N002["rule_by_key = {}"]
    N003["for f in findings:     rule_by_key.setdefault((f.path, f.line), f.rule_id)"]
    N004["return [f'{path}<str>{line}<str>{rule_by_key.get((path, line), '<str>')}<str>' for path, line in sorted(keys)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## render_markdown(...)

```mermaid
flowchart TD
    N001["render_markdown(...)"]
    N002["lines = [f'<str>{title}', '<str>']"]
    N003["append(...)"]
    N004["append(...)"]
    N005["for r in records:     lines.append(f'<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>{r['<str>']}<str>')"]
    N006["append(...)"]
    N007["append(...)"]
    N008["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## render_detail(...)

```mermaid
flowchart TD
    N001["render_detail(...)"]
    N002["lines = [f'<str>{pair_name}<str>', '<str>']"]
    N003["for label, keys, findings in (('<str>', new_only, new_findings), ('<str>', gate_only, gate_findings)):     listed = _format_locations(keys, findings)     lines.append(f'<str>{label}<str>{len(listed)}<str>')     for item in listed[:_MAX_LISTED]:         lines.append(f'<str>{item}')     if len(listed) > _MAX_LISTED:         lines.append(f'<str>{len(listed) - _MAX_LISTED}<str>')"]
    N004["append(...)"]
    N005["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## collect_workflow_static_gate(...)

```mermaid
flowchart TD
    N001["collect_workflow_static_gate(...)"]
    N002["findings = []"]
    N003["for v in scan_workflow_injection.find_violations(repo_root / '<str>' / '<str>'):     findings.append(Finding(rule_id='<str>', path=f'<str>{v.workflow}', line=v.line))"]
    N004["for rel_path, line, _reason in scan_workflow_action_pins.find_violations(repo_root):     findings.append(Finding(rule_id='<str>', path=rel_path.as_posix(), line=line))"]
    N005["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## collect_markdown_links_gate(...)

```mermaid
flowchart TD
    N001["collect_markdown_links_gate(...)"]
    N002["findings = []"]
    N003["for md in scan_markdown_links.iter_markdown_files(repo_root):     for link in scan_markdown_links.iter_links(md):         if scan_markdown_links.verify_link(link, repo_root) is not None:             findings.append(Finding(rule_id='<str>', path=scan_markdown_links.rel(link.source, repo_root), line=link.line))"]
    N004["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## collect_secrets_gate(...)

```mermaid
flowchart TD
    N001["collect_secrets_gate(...)"]
    N002["return [Finding(rule_id=f.rule_id, path=f.path.as_posix(), line=f.line) for f in scan_secrets.find_violations(repo_root)]"]
    N001 -->|"start"| N002
```

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["start = monotonic(...)"]
    N003["try"]
    N004["proc = run(...)"]
    N005["except FileNotFoundError"]
    N006["raise ToolUnavailableError(f'<str>{argv[0]}<str>')"]
    N007["duration_ms = (time.monotonic() - start) * 1000.0"]
    N008["return (proc.stdout, duration_ms)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 --> N008
```

## zizmor_argv(...)

```mermaid
flowchart TD
    N001["zizmor_argv(...)"]
    N002["return ['<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>']"]
    N001 -->|"start"| N002
```

## lychee_argv(...)

```mermaid
flowchart TD
    N001["lychee_argv(...)"]
    N002["return ['<str>', '<str>', '<str>', '<str>', '<str>', *md_files]"]
    N001 -->|"start"| N002
```

## betterleaks_argv(...)

```mermaid
flowchart TD
    N001["betterleaks_argv(...)"]
    N002["return ['<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>', '<str>']"]
    N001 -->|"start"| N002
```

## run_zizmor(...)

```mermaid
flowchart TD
    N001["run_zizmor(...)"]
    N002["(stdout, ms) = _run(...)"]
    N003["return (parse_zizmor(stdout), ms)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## run_lychee(...)

```mermaid
flowchart TD
    N001["run_lychee(...)"]
    N002["md_files = [scan_markdown_links.rel(p, repo_root) for p in scan_markdown_links.iter_markdown_files(repo_root)]"]
    N003["(stdout, ms) = _run(...)"]
    N004["return (parse_lychee(stdout), ms)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## run_betterleaks(...)

```mermaid
flowchart TD
    N001["run_betterleaks(...)"]
    N002["(stdout, ms) = _run(...)"]
    N003["return (parse_betterleaks(stdout, repo_root), ms)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _zizmor_smoke_argv(...)

```mermaid
flowchart TD
    N001["_zizmor_smoke_argv(...)"]
    N002["return zizmor_argv()"]
    N001 -->|"start"| N002
```

## _lychee_smoke_argv(...)

```mermaid
flowchart TD
    N001["_lychee_smoke_argv(...)"]
    N002["md_files = [scan_markdown_links.rel(p, repo_root) for p in scan_markdown_links.iter_markdown_files(repo_root)]"]
    N003["return lychee_argv(md_files)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _betterleaks_smoke_argv(...)

```mermaid
flowchart TD
    N001["_betterleaks_smoke_argv(...)"]
    N002["return betterleaks_argv()"]
    N001 -->|"start"| N002
```

## measure_pair(...)

```mermaid
flowchart TD
    N001["measure_pair(...)"]
    N002["(new_findings, new_ms) = run_tool(...)"]
    N003["gate_start = monotonic(...)"]
    N004["gate_findings = collect_gate(...)"]
    N005["gate_ms = (time.monotonic() - gate_start) * 1000.0"]
    N006["measured = now_ns(...)"]
    N007["record = build_record(...)"]
    N008["return (record, new_findings, gate_findings)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## smoke_pair(...)

```mermaid
flowchart TD
    N001["smoke_pair(...)"]
    N002["if run is None"]
    N003["run = _run"]
    N004["if spec.argv_builder is None"]
    N005["return SmokeResult(spec.pair_name, spec.new_tool, '<str>', '<str>')"]
    N006["argv = argv_builder(...)"]
    N007["try"]
    N008["(stdout, _ms) = run(...)"]
    N009["except ToolUnavailableError"]
    N010["return SmokeResult(spec.pair_name, spec.new_tool, '<str>', str(exc))"]
    N011["if not stdout.strip()"]
    N012["return SmokeResult(spec.pair_name, spec.new_tool, '<str>', f'{spec.new_tool}<str>{argv!r}<str>')"]
    N013["try"]
    N014["loads(...)"]
    N015["except json.JSONDecodeError"]
    N016["return SmokeResult(spec.pair_name, spec.new_tool, '<str>', f'{spec.new_tool}<str>{argv!r}<str>{exc}')"]
    N017["return SmokeResult(spec.pair_name, spec.new_tool, '<str>', f'{spec.new_tool}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
```

## cmd_smoke(...)

```mermaid
flowchart TD
    N001["cmd_smoke(...)"]
    N002["failed = False"]
    N003["for spec in specs:     result = smoke_pair(spec, repo_root)     if result.status == '<str>':         failed = True         print(f'<str>{result.pair_name}<str>{result.tool}<str>{result.detail}', file=sys.stderr)     else:         print(f'<str>{result.pair_name}<str>{result.tool}<str>{result.status}<str>{result.detail}')"]
    N004["return 1 if failed else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _resolve_commit(...)

```mermaid
flowchart TD
    N001["_resolve_commit(...)"]
    N002["if explicit"]
    N003["return explicit"]
    N004["try"]
    N005["out = run(...)"]
    N006["except FileNotFoundError"]
    N007["return '<str>'"]
    N008["sha = strip(...)"]
    N009["return sha or '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 --> N009
```

## _select_pairs(...)

```mermaid
flowchart TD
    N001["_select_pairs(...)"]
    N002["if name is None"]
    N003["return PAIRS"]
    N004["selected = tuple(...)"]
    N005["if not selected"]
    N006["valid = join(...)"]
    N007["raise ValueError(f'<str>{name}<str>{valid}')"]
    N008["return selected"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["return parser"]
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
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["import os"]
    N003["args = parse_args(...)"]
    N004["repo_root = resolve(...)"]
    N005["specs = _select_pairs(...)"]
    N006["if args.smoke"]
    N007["return cmd_smoke(specs, repo_root)"]
    N008["commit_sha = _resolve_commit(...)"]
    N009["host_id = args.host_id or os.environ.get('<str>', '<str>')"]
    N010["records = []"]
    N011["details = []"]
    N012["for spec in specs:     record, new_findings, gate_findings = measure_pair(spec, repo_root, commit_sha=commit_sha, host_id=host_id, notes=args.notes)     records.append(record)     _agree, new_only, gate_only = diff_findings(new_findings, gate_findings)     details.append(render_detail(spec.pair_name, new_only, gate_only, new_findings, gate_findings))"]
    N013["report = render_markdown(records, args.title) + '<str>' + '<str>'.join(details)"]
    N014["if args.output"]
    N015["write_text(...)"]
    N016["if args.report"]
    N017["write_text(...)"]
    N018["write(...)"]
    N019["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N017 --> N019
    N018 --> N019
```
