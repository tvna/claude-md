# AST graph: scripts/_git.py

This file is generated from `scripts/_git.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## run_git(...)

```mermaid
flowchart TD
    N001["run_git(...)"]
    N002["git = which(...)"]
    N003["if git is None"]
    N004["raise RuntimeError('<str>')"]
    N005["return subprocess.run([git, *args], cwd=cwd, check=check, capture_output=True, text=True, timeout=timeout)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## make_runner(...)

```mermaid
flowchart TD
    N001["make_runner(...)"]
    N002["def runner(args: list[str]) -> subprocess.CompletedProcess[str]:     return run_git(args, cwd=cwd, timeout=timeout)"]
    N003["return runner"]
    N001 -->|"start"| N002
    N002 --> N003
```

## rev_list(...)

```mermaid
flowchart TD
    N001["rev_list(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["return [line.strip() for line in result.stdout.splitlines() if line.strip()]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## is_all_zeros(...)

```mermaid
flowchart TD
    N001["is_all_zeros(...)"]
    N002["return ALL_ZEROS_RE.match(oid) is not None"]
    N001 -->|"start"| N002
```

## resolve_remote_name(...)

```mermaid
flowchart TD
    N001["resolve_remote_name(...)"]
    N002["if not remote"]
    N003["return None"]
    N004["try"]
    N005["result = runner(...)"]
    N006["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N007["return None"]
    N008["if result.returncode != 0"]
    N009["return None"]
    N010["names = set(...)"]
    N011["url_to_name = {}"]
    N012["for line in result.stdout.splitlines():     fields = line.split()     if len(fields) < 2:         continue     name, url = (fields[0], fields[1])     names.add(name)     url_to_name.setdefault(url, name)"]
    N013["if remote in names"]
    N014["return remote"]
    N015["return url_to_name.get(remote)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## commits_to_push(...)

```mermaid
flowchart TD
    N001["commits_to_push(...)"]
    N002["if remote_sha is not None and is_all_zeros(remote_sha)"]
    N003["remote_sha = None"]
    N004["if remote_sha is not None"]
    N005["rev_args = [f'{remote_sha}<str>{local_sha}']"]
    N006["scoped = resolve_remote_name(...)"]
    N007["if scoped"]
    N008["rev_args = [local_sha, '<str>', f'<str>{scoped}']"]
    N009["rev_args = [local_sha, '<str>', '<str>']"]
    N010["return rev_list(runner, rev_args)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N005 --> N010
    N008 --> N010
    N009 --> N010
```
