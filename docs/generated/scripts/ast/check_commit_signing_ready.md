# AST graph: scripts/check_commit_signing_ready.py

This file is generated from `scripts/check_commit_signing_ready.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _command_runs_git_commit(...)

```mermaid
flowchart TD
    N001["_command_runs_git_commit(...)"]
    N002["if _GIT_COMMIT_RE.search(command)"]
    N003["return True"]
    N004["try"]
    N005["tokens = split(...)"]
    N006["except ValueError"]
    N007["return False"]
    N008["i = 0"]
    N009["while i < len(tokens):     if tokens[i] != '<str>' and (not tokens[i].endswith('<str>')):         i += 1         continue     j = i + 1     while j < len(tokens):         arg = tokens[j]         if arg.startswith('<str>'):             j += 2 if arg in _GIT_VALUE_OPTS else 1             continue         if arg.rstrip('<str>') == '<str>':             return True         break     i = j + 1"]
    N010["return False"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 --> N009
    N009 --> N010
```

## _is_remote(...)

```mermaid
flowchart TD
    N001["_is_remote(...)"]
    N002["return any((os.environ.get(var, '<str>').lower() == '<str>' for var in _REMOTE_ENV_VARS))"]
    N001 -->|"start"| N002
```

## _git_config_get(...)

```mermaid
flowchart TD
    N001["_git_config_get(...)"]
    N002["try"]
    N003["result = run_git(...)"]
    N004["except (RuntimeError, OSError)"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["value = strip(...)"]
    N009["return value or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## signing_required(...)

```mermaid
flowchart TD
    N001["signing_required(...)"]
    N002["try"]
    N003["result = run_git(...)"]
    N004["except (RuntimeError, OSError)"]
    N005["return False"]
    N006["if result.returncode != 0"]
    N007["return False"]
    N008["return result.stdout.strip().lower() == '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## probe_sign_status(...)

```mermaid
flowchart TD
    N001["probe_sign_status(...)"]
    N002["try"]
    N003["tmp = mkdtemp(...)"]
    N004["except OSError"]
    N005["return '<str>'"]
    N006["try"]
    N007["init = run_git(...)"]
    N008["if init.returncode != 0"]
    N009["return '<str>'"]
    N010["run_git(...)"]
    N011["run_git(...)"]
    N012["run_git(...)"]
    N013["for key in _SIGNING_CONFIG_KEYS:     value = _git_config_get(key)     if value is not None:         run_git(['<str>', tmp, '<str>', key, value], timeout=_GIT_TIMEOUT_SECONDS)"]
    N014["commit = run_git(...)"]
    N015["if commit.returncode != 0"]
    N016["return '<str>'"]
    N017["cat = run_git(...)"]
    N018["if cat.returncode != 0"]
    N019["return '<str>'"]
    N020["for line in cat.stdout.splitlines():     if line.startswith('<str>'):         return '<str>'"]
    N021["return '<str>'"]
    N022["except (RuntimeError, OSError, subprocess.TimeoutExpired)"]
    N023["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
    N006 -->|"raises"| N022
    N022 --> N023
```

## _build_warning(...)

```mermaid
flowchart TD
    N001["_build_warning(...)"]
    N002["return '<str>'"]
    N001 -->|"start"| N002
```

## _build_deny_reason(...)

```mermaid
flowchart TD
    N001["_build_deny_reason(...)"]
    N002["return f'<str>{_ACK_MARKER}<str>'"]
    N001 -->|"start"| N002
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

## cmd_session_start(...)

```mermaid
flowchart TD
    N001["cmd_session_start(...)"]
    N002["if not _is_remote()"]
    N003["return 0"]
    N004["try"]
    N005["if not signing_required()"]
    N006["return 0"]
    N007["status = probe_sign_status(...)"]
    N008["except Exception"]
    N009["return 0"]
    N010["if status == 'unsigned'"]
    N011["_emit_context(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N004 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
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
    N007["if not _command_runs_git_commit(command)"]
    N008["return None"]
    N009["if _ACK_MARKER in command"]
    N010["return None"]
    N011["try"]
    N012["if not signing_required()"]
    N013["return None"]
    N014["status = probe_sign_status(...)"]
    N015["except Exception"]
    N016["return None"]
    N017["if status == 'unsigned'"]
    N018["return build_deny(_build_deny_reason())"]
    N019["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"try"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N011 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
```

## cmd_check(...)

```mermaid
flowchart TD
    N001["cmd_check(...)"]
    N002["try"]
    N003["if not signing_required()"]
    N004["print(...)"]
    N005["return 0"]
    N006["status = probe_sign_status(...)"]
    N007["except Exception"]
    N008["print(...)"]
    N009["return 0"]
    N010["if status == 'signed'"]
    N011["print(...)"]
    N012["return 0"]
    N013["if status == 'unsigned'"]
    N014["print(...)"]
    N015["return 1"]
    N016["print(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N002 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 --> N017
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_ss = add_parser(...)"]
    N005["set_defaults(...)"]
    N006["p_check = add_parser(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["if args.cmd is None"]
    N010["return run_event_hook('<str>', decide, auditable=False)"]
    N011["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```
