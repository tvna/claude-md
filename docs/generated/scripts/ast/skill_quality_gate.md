# AST graph: scripts/skill_quality_gate.py

This file is generated from `scripts/skill_quality_gate.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## find_waza(...)

```mermaid
flowchart TD
    N001["find_waza(...)"]
    N002["found = which(...)"]
    N003["if found"]
    N004["return found"]
    N005["for hint in _GO_BIN_HINTS:     candidate = hint / '<str>'     if candidate.is_file():         return str(candidate)"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## discover_skills(...)

```mermaid
flowchart TD
    N001["discover_skills(...)"]
    N002["skills_dir = repo_root / SKILLS_SUBDIR"]
    N003["return sorted((p.parent for p in skills_dir.glob('<str>') if p.is_file()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _normalize_target(...)

```mermaid
flowchart TD
    N001["_normalize_target(...)"]
    N002["path = Path(...)"]
    N003["if not path.is_absolute()"]
    N004["path = repo_root / path"]
    N005["if path.name == 'SKILL.md'"]
    N006["path = path.parent"]
    N007["if (path / 'SKILL.md').is_file()"]
    N008["return path"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## run_waza_check(...)

```mermaid
flowchart TD
    N001["run_waza_check(...)"]
    N002["proc = run(...)"]
    N003["if not proc.stdout.strip()"]
    N004["raise RuntimeError(f'<str>{skill_dir}<str>{proc.returncode}<str>{proc.stderr.strip()}')"]
    N005["try"]
    N006["return json.loads(proc.stdout)"]
    N007["except json.JSONDecodeError"]
    N008["raise RuntimeError(f'<str>{skill_dir}<str>{exc}<str>{proc.stderr.strip()}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
```

## evaluate_skill(...)

```mermaid
flowchart TD
    N001["evaluate_skill(...)"]
    N002["spec_failures = []"]
    N003["token_warnings = []"]
    N004["for check in entry.get('<str>', []):     if not check.get('<str>', True):         spec_failures.append(f'{check.get('<str>', '<str>')}<str>{check.get('<str>', '<str>')}')"]
    N005["budget = get(...)"]
    N006["if budget.get('exceeded')"]
    N007["append(...)"]
    N008["return (spec_failures, token_warnings)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["waza = find_waza(...)"]
    N004["if waza is None"]
    N005["print(...)"]
    N006["return 1"]
    N007["if args.skills"]
    N008["targets = []"]
    N009["for raw in args.skills:     target = _normalize_target(repo_root, raw)     if target is None:         print(f'<str>{raw}<str>', file=sys.stderr)         continue     targets.append(target)"]
    N010["targets = discover_skills(...)"]
    N011["if not targets"]
    N012["print(...)"]
    N013["return 0"]
    N014["total_failures = 0"]
    N015["for skill_dir in targets:     result = run_waza_check(waza, skill_dir)     for entry in result.get('<str>', []):         rel = Path(entry.get('<str>', str(skill_dir)))         with contextlib.suppress(ValueError):             rel = rel.relative_to(repo_root)         spec_failures, token_warnings = evaluate_skill(entry)         for msg in token_warnings:             print(f'<str>{rel}<str>{msg}<str>', file=sys.stderr)         for msg in spec_failures:             print(f'<str>{rel}<str>{msg}', file=sys.stderr)         if spec_failures:             total_failures += len(spec_failures)             print(f'<str>{rel}<str>{len(spec_failures)}<str>', file=sys.stderr)         else:             print(f'<str>{rel}')"]
    N016["if total_failures"]
    N017["print(...)"]
    N018["return 1"]
    N019["print(...)"]
    N020["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N009 --> N011
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 --> N020
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
