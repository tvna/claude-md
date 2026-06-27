# AST graph: scripts/preflight_session_base_freshness.py

This file is generated from `scripts/preflight_session_base_freshness.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _is_remote(...)

```mermaid
flowchart TD
    N001["_is_remote(...)"]
    N002["return os.environ.get(_REMOTE_ENV_VAR, '<str>').lower() == '<str>'"]
    N001 -->|"start"| N002
```

## _current_branch(...)

```mermaid
flowchart TD
    N001["_current_branch(...)"]
    N002["_repo = repo if repo is not None else REPO_ROOT"]
    N003["try"]
    N004["cp = run_git(...)"]
    N005["return cp.stdout.strip() or None"]
    N006["except Exception"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N004 --> N005
    N003 -->|"raises"| N006
    N006 --> N007
```

## _force_push_blocked(...)

```mermaid
flowchart TD
    N001["_force_push_blocked(...)"]
    N002["if branch is None"]
    N003["return False"]
    N004["if branch == 'main'"]
    N005["return False"]
    N006["return not branch.startswith('<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## base_is_stale(...)

```mermaid
flowchart TD
    N001["base_is_stale(...)"]
    N002["if repo is None"]
    N003["repo = REPO_ROOT"]
    N004["if stamp_path is None"]
    N005["stamp_path = STAMP_FILE"]
    N006["stamp = read_stamp(...)"]
    N007["if stamp is None"]
    N008["return None"]
    N009["result = check_base_freshness(...)"]
    N010["return result.status != '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
```

## _build_warning(...)

```mermaid
flowchart TD
    N001["_build_warning(...)"]
    N002["if force_push_blocked"]
    N003["remedy = f'<str>{_RUNBOOK}<str>'"]
    N004["remedy = '<str>'"]
    N005["return f'<str>{sha[:12]}<str>{remedy}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N003 --> N005
    N004 --> N005
```

## _build_deny_reason(...)

```mermaid
flowchart TD
    N001["_build_deny_reason(...)"]
    N002["if force_push_blocked"]
    N003["remedy = f'<str>{_RUNBOOK}<str>'"]
    N004["remedy = '<str>'"]
    N005["return f'<str>{sha[:12]}<str>{remedy}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N003 --> N005
    N004 --> N005
```

## _emit_context(...)

```mermaid
flowchart TD
    N001["_emit_context(...)"]
    N002["print(...)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _build_updated_notice(...)

```mermaid
flowchart TD
    N001["_build_updated_notice(...)"]
    N002["return f'<str>{sha[:12]}<str>'"]
    N001 -->|"start"| N002
```

## _try_auto_update_base(...)

```mermaid
flowchart TD
    N001["_try_auto_update_base(...)"]
    N002["try"]
    N003["status = run_git(...)"]
    N004["if status.returncode != 0 or status.stdout.strip()"]
    N005["return '<str>'"]
    N006["ancestor = run_git(...)"]
    N007["if ancestor.returncode != 0"]
    N008["return '<str>'"]
    N009["merged = run_git(...)"]
    N010["if merged.returncode != 0"]
    N011["return '<str>'"]
    N012["except Exception"]
    N013["return '<str>'"]
    N014["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N002 -->|"raises"| N012
    N012 --> N013
    N010 -->|"false"| N014
```

## cmd_session_start(...)

```mermaid
flowchart TD
    N001["cmd_session_start(...)"]
    N002["if not _is_remote()"]
    N003["return 0"]
    N004["try"]
    N005["stamp = fetch_and_record(...)"]
    N006["except Exception"]
    N007["return 0"]
    N008["try"]
    N009["result = check_base_freshness(...)"]
    N010["except Exception"]
    N011["return 0"]
    N012["if result.status != 'pass'"]
    N013["branch = _current_branch(...)"]
    N014["if branch is not None and _try_auto_update_base(stamp.sha, repo=REPO_ROOT) == 'updated'"]
    N015["_emit_context(...)"]
    N016["_emit_context(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N015 --> N017
    N016 --> N017
    N012 -->|"false"| N017
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if not _is_remote()"]
    N003["return None"]
    N004["if event.get('tool_name') != 'Bash'"]
    N005["return None"]
    N006["command = str(...)"]
    N007["if not _GIT_COMMIT_RE.search(command)"]
    N008["return None"]
    N009["try"]
    N010["stamp = read_stamp(...)"]
    N011["if stamp is None"]
    N012["return None"]
    N013["result = check_base_freshness(...)"]
    N014["except Exception"]
    N015["return None"]
    N016["if result.status == 'pass'"]
    N017["return None"]
    N018["branch = _current_branch(...)"]
    N019["return build_deny(_build_deny_reason(stamp.sha, force_push_blocked=_force_push_blocked(branch)))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"try"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N009 -->|"raises"| N014
    N014 --> N015
    N013 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 --> N019
```

## cmd_check(...)

```mermaid
flowchart TD
    N001["cmd_check(...)"]
    N002["stale = base_is_stale(...)"]
    N003["if stale is None"]
    N004["print(...)"]
    N005["return 0"]
    N006["if not stale"]
    N007["print(...)"]
    N008["return 0"]
    N009["branch = _current_branch(...)"]
    N010["if _force_push_blocked(branch)"]
    N011["print(...)"]
    N012["print(...)"]
    N013["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N011 --> N013
    N012 --> N013
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_ss = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["p_check = add_parser(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["if args.cmd is None"]
    N012["return run_event_hook('<str>', decide, auditable=False)"]
    N013["return args.func(args)"]
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
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```
