# AST graph: scripts/scan_runbook_template_drift.py

This file is generated from `scripts/scan_runbook_template_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _fence_at(...)

```mermaid
flowchart TD
    N001["_fence_at(...)"]
    N002["indent = len(line) - len(line.lstrip('<str>'))"]
    N003["if indent > 3"]
    N004["return None"]
    N005["s = line[indent:]"]
    N006["if not s or s[0] not in ('`', '~')"]
    N007["return None"]
    N008["char = s[0]"]
    N009["run = len(s) - len(s.lstrip(char))"]
    N010["if run < 3"]
    N011["return None"]
    N012["return (char, run, s[run:])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
```

## _strip_fenced_code_blocks(...)

```mermaid
flowchart TD
    N001["_strip_fenced_code_blocks(...)"]
    N002["out = []"]
    N003["open_char = None"]
    N004["open_len = 0"]
    N005["for line in text.splitlines():     fence = _fence_at(line)     if open_char is None:         if fence is not None:             char, run, info = fence             if not (char == '<str>' and '<str>' in info):                 open_char, open_len = (char, run)                 out.append('<str>')                 continue         out.append(line)     else:         if fence is not None:             char, run, info = fence             if char == open_char and run >= open_len and (not info.strip()):                 open_char, open_len = (None, 0)         out.append('<str>')"]
    N006["return '<str>'.join(out)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## extract_h2_headings(...)

```mermaid
flowchart TD
    N001["extract_h2_headings(...)"]
    N002["return [m.group(1).strip() for m in _H2_RE.finditer(_strip_fenced_code_blocks(text))]"]
    N001 -->|"start"| N002
```

## check_conformance(...)

```mermaid
flowchart TD
    N001["check_conformance(...)"]
    N002["problems = []"]
    N003["for section in REQUIRED_SECTIONS:     if section not in headings:         problems.append(f'<str>{section}<str>')"]
    N004["present = [h for h in headings if h in REQUIRED_SECTIONS]"]
    N005["canonical_order = [s for s in REQUIRED_SECTIONS if s in present]"]
    N006["if present != canonical_order"]
    N007["append(...)"]
    N008["return problems"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```

## parse_waivers(...)

```mermaid
flowchart TD
    N001["parse_waivers(...)"]
    N002["return frozenset((m.group(1) for m in _WAIVER_RE.finditer(body)))"]
    N001 -->|"start"| N002
```

## _is_runbook(...)

```mermaid
flowchart TD
    N001["_is_runbook(...)"]
    N002["p = Path(...)"]
    N003["return path.startswith(_RUNBOOK_DIR) and p.parent == _RUNBOOK_PARENT and (p.suffix == '<str>') and (path not in _EXCLUDED)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## get_changed_runbooks(...)

```mermaid
flowchart TD
    N001["get_changed_runbooks(...)"]
    N002["committed = run(...)"]
    N003["if committed.returncode != 0"]
    N004["return None"]
    N005["names = {f.strip() for f in committed.stdout.splitlines() if f.strip()}"]
    N006["cached = run(...)"]
    N007["if cached.returncode == 0"]
    N008["names |= {f.strip() for f in cached.stdout.splitlines() if f.strip()}"]
    N009["return sorted((n for n in names if _is_runbook(n)))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
```

## run_gate(...)

```mermaid
flowchart TD
    N001["run_gate(...)"]
    N002["if not changed"]
    N003["print(...)"]
    N004["return True"]
    N005["passed = True"]
    N006["for path in changed:     if path in waivers:         print(f'<str>{path!r}<str>', file=sys.stderr)         continue     try:         text = read_text(path)     except OSError as exc:         print(f'<str>{_SCRIPT}<str>{path!r}<str>{exc}', file=sys.stderr)         continue     problems = check_conformance(extract_h2_headings(text))     if problems:         detail = '<str>'.join(problems)         print(f'<str>{path}<str>{_SCRIPT}<str>{path!r}<str>{detail}<str>{path}<str>', file=sys.stderr)         passed = False"]
    N007["if passed"]
    N008["print(...)"]
    N009["return passed"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
```

## _read_text(...)

```mermaid
flowchart TD
    N001["_read_text(...)"]
    N002["return Path(path).read_text(encoding='<str>')"]
    N001 -->|"start"| N002
```

## _audit_all(...)

```mermaid
flowchart TD
    N001["_audit_all(...)"]
    N002["any_problem = False"]
    N003["for path in sorted((str(p) for p in _RUNBOOK_PARENT.glob('<str>'))):     if path in _EXCLUDED:         continue     problems = check_conformance(extract_h2_headings(_read_text(path)))     if problems:         any_problem = True         print(f'<str>{path}<str>{_SCRIPT}<str>{'<str>'.join(problems)}', file=sys.stderr)"]
    N004["if not any_problem"]
    N005["print(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
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
    N013["args = parse_args(...)"]
    N014["if args.all"]
    N015["return _audit_all()"]
    N016["body = '<str>'"]
    N017["if args.body_file"]
    N018["try"]
    N019["body = read_text(...)"]
    N020["except OSError"]
    N021["print(...)"]
    N022["body = get(...)"]
    N023["waivers = parse_waivers(...)"]
    N024["changed = get_changed_runbooks(...)"]
    N025["if changed is None"]
    N026["print(...)"]
    N027["return 0"]
    N028["return 0 if run_gate(changed, _read_text, waivers) else 1"]
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
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 -->|"try"| N019
    N018 -->|"raises"| N020
    N020 --> N021
    N017 -->|"false"| N022
    N019 --> N023
    N021 --> N023
    N022 --> N023
    N023 --> N024
    N024 --> N025
    N025 -->|"true"| N026
    N026 --> N027
    N025 -->|"false"| N028
```
