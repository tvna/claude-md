# AST graph: scripts/coverage_failure_issue.py

This file is generated from `scripts/coverage_failure_issue.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _require_env(...)

```mermaid
flowchart TD
    N001["_require_env(...)"]
    N002["missing = [name for name in names if not env.get(name)]"]
    N003["if missing"]
    N004["raise RuntimeError(f\"<str>{'<str>'.join(missing)}\")"]
    N005["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## context_from_env(...)

```mermaid
flowchart TD
    N001["context_from_env(...)"]
    N002["_require_env(...)"]
    N003["repo = env['<str>']"]
    N004["run_id = env['<str>']"]
    N005["run_attempt = get(...)"]
    N006["server_url = rstrip(...)"]
    N007["workflow = get(...)"]
    N008["coverage_result = get(...)"]
    N009["run_url = f'{server_url}<str>{repo}<str>{run_id}<str>{run_attempt}'"]
    N010["return CoverageFailureContext(repo=repo, run_url=run_url, workflow=workflow, coverage_result=coverage_result, run_id=run_id, run_attempt=run_attempt)"]
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

## render_comment(...)

```mermaid
flowchart TD
    N001["render_comment(...)"]
    N002["return f'<str>{context.workflow}<str>{context.coverage_result}<str>{context.run_url}<str>{COVERAGE_GATE}<str>{context.run_id}<str>{context.run_attempt}<str>'"]
    N001 -->|"start"| N002
```

## _run_gh(...)

```mermaid
flowchart TD
    N001["_run_gh(...)"]
    N002["kwargs = {'<str>': True, '<str>': True, '<str>': 30, '<str>': True}"]
    N003["if body is not None"]
    N004["cmd = [*cmd, '<str>', body]"]
    N005["return runner(cmd, **kwargs)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## post_failure_comment(...)

```mermaid
flowchart TD
    N001["post_failure_comment(...)"]
    N002["_run_gh(...)"]
    N003["print(...)"]
    N004["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["args = parse_args(...)"]
    N006["if args.command == 'run'"]
    N007["try"]
    N008["context = context_from_env(...)"]
    N009["post_failure_comment(...)"]
    N010["except (RuntimeError, subprocess.CalledProcessError)"]
    N011["print(...)"]
    N012["return 1"]
    N013["return 0"]
    N014["error(...)"]
    N015["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 -->|"try"| N008
    N008 --> N009
    N007 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N006 -->|"false"| N014
    N014 --> N015
```
