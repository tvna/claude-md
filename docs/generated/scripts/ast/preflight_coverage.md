# AST graph: scripts/preflight_coverage.py

This file is generated from `scripts/preflight_coverage.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## changed_scripts(...)

```mermaid
flowchart TD
    N001["changed_scripts(...)"]
    N002["completed = run_git(...)"]
    N003["if completed.returncode != 0"]
    N004["detail = strip(...)"]
    N005["raise RuntimeError(f'<str>{base_ref}<str>{detail}')"]
    N006["return [line.strip() for line in completed.stdout.splitlines() if line.strip().startswith('<str>') and line.strip().endswith('<str>') and (not Path(line.strip()).name.startswith('<str>'))]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## newest_source_mtime(...)

```mermaid
flowchart TD
    N001["newest_source_mtime(...)"]
    N002["newest = None"]
    N003["for sub in ('<str>', '<str>'):     base = repo / sub     if not base.is_dir():         continue     for path in base.rglob('<str>'):         try:             mtime = path.stat().st_mtime         except OSError:             continue         if newest is None or mtime > newest:             newest = mtime"]
    N004["return newest"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## coverage_is_stale(...)

```mermaid
flowchart TD
    N001["coverage_is_stale(...)"]
    N002["try"]
    N003["cov_mtime = coverage_path.stat().st_mtime"]
    N004["except OSError"]
    N005["return True"]
    N006["newest = newest_source_mtime(...)"]
    N007["if newest is None"]
    N008["return False"]
    N009["return cov_mtime <= newest"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## ensure_coverage_json(...)

```mermaid
flowchart TD
    N001["ensure_coverage_json(...)"]
    N002["coverage_path = repo / '<str>'"]
    N003["stale_mtime = None"]
    N004["if coverage_path.exists()"]
    N005["if not coverage_is_stale(coverage_path, repo)"]
    N006["return coverage_path"]
    N007["print(...)"]
    N008["with contextlib.suppress(OSError):     stale_mtime = coverage_path.stat().st_mtime"]
    N009["with contextlib.suppress(OSError):     coverage_path.unlink()"]
    N010["uv = which(...)"]
    N011["if uv is None"]
    N012["raise RuntimeError('<str>')"]
    N013["completed = run(...)"]
    N014["if not coverage_path.exists()"]
    N015["raise RuntimeError(f'<str>{completed.returncode}<str>')"]
    N016["if stale_mtime is not None and coverage_path.stat().st_mtime == stale_mtime"]
    N017["raise RuntimeError(f'<str>{completed.returncode}<str>')"]
    N018["return coverage_path"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N004 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## parse_coverage_json(...)

```mermaid
flowchart TD
    N001["parse_coverage_json(...)"]
    N002["data = loads(...)"]
    N003["files = get(...)"]
    N004["if not isinstance(files, dict)"]
    N005["return {}"]
    N006["result = {}"]
    N007["for file_path, info in files.items():     if not isinstance(info, dict):         continue     summary = info.get('<str>', {})     if not isinstance(summary, dict):         continue     pct = summary.get('<str>')     if isinstance(pct, int | float):         result[str(file_path)] = float(pct)"]
    N008["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
```

## check_per_file(...)

```mermaid
flowchart TD
    N001["check_per_file(...)"]
    N002["failures = []"]
    N003["for target in targets:     if target not in coverage:         failures.append((target, '<str>'))         continue     pct = coverage[target]     if pct < floor:         failures.append((target, f'{pct:<str>}<str>{floor:<str>}<str>'))"]
    N004["return failures"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["try"]
    N008["targets = changed_scripts(...)"]
    N009["except RuntimeError"]
    N010["print(...)"]
    N011["return 1"]
    N012["if not targets"]
    N013["print(...)"]
    N014["return 0"]
    N015["cov_path"]
    N016["if args.coverage_json is not None"]
    N017["cov_path = Path(...)"]
    N018["try"]
    N019["cov_path = ensure_coverage_json(...)"]
    N020["except RuntimeError"]
    N021["print(...)"]
    N022["return 1"]
    N023["try"]
    N024["coverage = parse_coverage_json(...)"]
    N025["except (json.JSONDecodeError, OSError)"]
    N026["print(...)"]
    N027["return 1"]
    N028["failures = check_per_file(...)"]
    N029["failure_paths = {f[0] for f in failures}"]
    N030["for target in targets:     if target not in failure_paths:         pct = coverage.get(target, 0.0)         print(f'<str>{target}<str>{pct:<str>}<str>{args.floor:<str>}<str>')"]
    N031["for path, reason in failures:     print(f'<str>{path}<str>{reason}', file=sys.stderr)"]
    N032["if failures"]
    N033["print(...)"]
    N034["return 1"]
    N035["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 -->|"try"| N019
    N018 -->|"raises"| N020
    N020 --> N021
    N021 --> N022
    N017 --> N023
    N019 --> N023
    N023 -->|"try"| N024
    N023 -->|"raises"| N025
    N025 --> N026
    N026 --> N027
    N024 --> N028
    N028 --> N029
    N029 --> N030
    N030 --> N031
    N031 --> N032
    N032 -->|"true"| N033
    N033 --> N034
    N032 -->|"false"| N035
```
