# AST graph: scripts/preflight_all.py

This file is generated from `scripts/preflight_all.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## missing_prereqs(...)

```mermaid
flowchart TD
    N001["missing_prereqs(...)"]
    N002["missing = []"]
    N003["for key in step.required_env:     if not environ.get(key):         missing.append(f'<str>{key}')"]
    N004["for binary in step.required_bin:     if shutil.which(binary) is None:         missing.append(f'<str>{binary}')"]
    N005["return missing"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## run_step(...)

```mermaid
flowchart TD
    N001["run_step(...)"]
    N002["missing = missing_prereqs(...)"]
    N003["if missing"]
    N004["detail = '<str>' + '<str>'.join(missing)"]
    N005["return StepResult(name=step.name, status='<str>' if step.soft else '<str>', detail=detail)"]
    N006["start = monotonic(...)"]
    N007["completed = run(...)"]
    N008["elapsed = time.monotonic() - start"]
    N009["if completed.returncode == 0"]
    N010["return StepResult(name=step.name, status='<str>', duration_s=elapsed)"]
    N011["return StepResult(name=step.name, status='<str>', detail=f'<str>{completed.returncode}', duration_s=elapsed)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## _heavy_fingerprint(...)

```mermaid
flowchart TD
    N001["_heavy_fingerprint(...)"]
    N002["extra = tuple(...)"]
    N003["try"]
    N004["return preflight_cache.compute_fingerprint(cwd, extra=extra)"]
    N005["except (OSError, subprocess.SubprocessError)"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
```

## _cheap_workers(...)

```mermaid
flowchart TD
    N001["_cheap_workers(...)"]
    N002["override = strip(...)"]
    N003["if override"]
    N004["try"]
    N005["value = int(...)"]
    N006["except ValueError"]
    N007["value = 0"]
    N008["if value >= 1"]
    N009["return max(1, min(value, n))"]
    N010["return max(1, min(n, (os.cpu_count() or 4) * 2, 16))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N003 -->|"false"| N010
```

## _run_cheap(...)

```mermaid
flowchart TD
    N001["_run_cheap(...)"]
    N002["serial = [s for s in cheap if s.name in _SERIAL_CHEAP]"]
    N003["parallel = [s for s in cheap if s.name not in _SERIAL_CHEAP]"]
    N004["results = {}"]
    N005["for step in serial:     results[step.name] = run_step(step, cwd, environ)"]
    N006["if parallel"]
    N007["workers = _cheap_workers(...)"]
    N008["if workers == 1"]
    N009["for step in parallel:     results[step.name] = run_step(step, cwd, environ)"]
    N010["with ThreadPoolExecutor(max_workers=workers) as pool:     futures = {pool.submit(run_step, step, cwd, environ): step.name for step in parallel}     for future in as_completed(futures):         results[futures[future]] = future.result()"]
    N011["return [results[step.name] for step in cheap]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N009 --> N011
    N010 --> N011
    N006 -->|"false"| N011
```

## run_all(...)

```mermaid
flowchart TD
    N001["run_all(...)"]
    N002["cheap = [s for s in steps if not s.heavy]"]
    N003["heavy = [s for s in steps if s.heavy]"]
    N004["cheap_results = _run_cheap(...)"]
    N005["cheap_failed = [r.name for r in cheap_results if r.status == '<str>']"]
    N006["if not heavy"]
    N007["return cheap_results"]
    N008["if cheap_failed"]
    N009["blocked = '<str>' + '<str>'.join(cheap_failed)"]
    N010["heavy_results = [StepResult(name=step.name, status='<str>', detail=blocked) for step in heavy]"]
    N011["return cheap_results + heavy_results"]
    N012["fingerprint = _heavy_fingerprint(...)"]
    N013["cache_file = cache_path(...)"]
    N014["cache = load(...)"]
    N015["disabled = cache_disabled(...)"]
    N016["fresh = not disabled and fingerprint is not None and preflight_cache.is_fresh(cache, fingerprint)"]
    N017["heavy_results = []"]
    N018["ran_any = False"]
    N019["for step in heavy:     if fresh:         ts = cache.get('<str>', '<str>') if cache else '<str>'         heavy_results.append(StepResult(name=step.name, status='<str>', detail=f'<str>{ts}'))     else:         heavy_results.append(run_step(step, cwd, environ))         ran_any = True"]
    N020["if ran_any and fingerprint is not None and all((r.status == 'pass' for r in heavy_results))"]
    N021["record(...)"]
    N022["return cheap_results + heavy_results"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 --> N011
    N008 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N022
```

## emit_summary(...)

```mermaid
flowchart TD
    N001["emit_summary(...)"]
    N002["width = max(...)"]
    N003["for result in results:     line = f'{result.status:<str>}<str>{result.name:<str>{width}}<str>{result.duration_s:<str>}<str>'     if result.detail:         line = f'{line}<str>{result.detail}'     print(line, file=stream)"]
    N004["total = sum(...)"]
    N005["print(...)"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## emit_annotations(...)

```mermaid
flowchart TD
    N001["emit_annotations(...)"]
    N002["for result in results:     if result.status == '<str>':         print(f'<str>{result.name}<str>{result.detail}<str>', file=stream)     elif result.status == '<str>':         print(f'<str>{result.name}<str>{result.detail}<str>', file=stream)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## resolve_skips(...)

```mermaid
flowchart TD
    N001["resolve_skips(...)"]
    N002["names = set(...)"]
    N003["env = get(...)"]
    N004["names |= {part.strip() for part in env.split('<str>') if part.strip()}"]
    N005["return names"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## partition_skips(...)

```mermaid
flowchart TD
    N001["partition_skips(...)"]
    N002["known = {step.name for step in steps}"]
    N003["unknown = sorted(...)"]
    N004["to_run = [step for step in steps if step.name not in skip]"]
    N005["skipped = [StepResult(name=step.name, status='<str>', detail='<str>') for step in steps if step.name in skip]"]
    N006["return (to_run, skipped, unknown)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## list_manifest(...)

```mermaid
flowchart TD
    N001["list_manifest(...)"]
    N002["return [{'<str>': step.name, '<str>': list(step.argv), '<str>': list(step.required_env), '<str>': list(step.required_bin), '<str>': step.soft, '<str>': step.heavy} for step in STEPS]"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["args = parse_args(...)"]
    N006["if args.list"]
    N007["dump(...)"]
    N008["write(...)"]
    N009["return 0"]
    N010["environ = dict(...)"]
    N011["skip = resolve_skips(...)"]
    N012["(to_run, skipped, unknown) = partition_skips(...)"]
    N013["for name in unknown:     print(f'<str>{name}<str>', file=sys.stderr)"]
    N014["results = run_all(to_run, REPO_ROOT, environ) + skipped"]
    N015["emit_summary(...)"]
    N016["emit_annotations(...)"]
    N017["fails = sum(...)"]
    N018["return 0 if fails == 0 else 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
```
