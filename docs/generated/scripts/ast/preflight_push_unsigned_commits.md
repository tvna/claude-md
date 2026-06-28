# AST graph: scripts/preflight_push_unsigned_commits.py

This file is generated from `scripts/preflight_push_unsigned_commits.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _default_runner(...)

```mermaid
flowchart TD
    N001["_default_runner(...)"]
    N002["return run_git(args, timeout=_GIT_TIMEOUT_SECONDS)"]
    N001 -->|"start"| N002
```

## _is_remote(...)

```mermaid
flowchart TD
    N001["_is_remote(...)"]
    N002["return any((os.environ.get(var, '<str>').lower() == '<str>' for var in _REMOTE_ENV_VARS))"]
    N001 -->|"start"| N002
```

## _basename(...)

```mermaid
flowchart TD
    N001["_basename(...)"]
    N002["return PurePosixPath(token.strip().strip('<str>')).name"]
    N001 -->|"start"| N002
```

## _push_args_in_segment(...)

```mermaid
flowchart TD
    N001["_push_args_in_segment(...)"]
    N002["try"]
    N003["tokens = split(...)"]
    N004["except ValueError"]
    N005["return None"]
    N006["idx = 0"]
    N007["while idx < len(tokens) and _ASSIGN_RE.match(tokens[idx]):     idx += 1"]
    N008["if idx < len(tokens) and _basename(tokens[idx]) == 'rtk'"]
    N009["idx += 1"]
    N010["if idx >= len(tokens) or _basename(tokens[idx]) != 'git'"]
    N011["return None"]
    N012["rest = tokens[idx + 1:]"]
    N013["j = 0"]
    N014["while j < len(rest) and rest[j].startswith('<str>'):     j += 2 if rest[j] in _GIT_VALUE_OPTS else 1"]
    N015["if j >= len(rest) or rest[j] != 'push'"]
    N016["return None"]
    N017["return rest[j + 1:]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## _specs_from_push_args(...)

```mermaid
flowchart TD
    N001["_specs_from_push_args(...)"]
    N002["positionals = []"]
    N003["i = 0"]
    N004["end_of_opts = False"]
    N005["while i < len(args):     tok = args[i]     if not end_of_opts and tok == '<str>':         end_of_opts = True         i += 1         continue     if not end_of_opts and tok.startswith('<str>'):         if '<str>' in tok or tok in _FLAGS_NO_VALUE:             i += 1         elif tok in _FLAGS_WITH_VALUE:             i += 2         else:             i += 1         continue     positionals.append(tok)     i += 1"]
    N006["if len(positionals) < 2"]
    N007["return []"]
    N008["remote = positionals[0]"]
    N009["specs = []"]
    N010["for raw in positionals[1:]:     refspec = raw[1:] if raw.startswith('<str>') else raw     if '<str>' in refspec:         local_ref, remote_ref = refspec.split('<str>', 1)         if not local_ref:             continue     else:         local_ref = remote_ref = refspec     if not remote_ref:         continue     specs.append((remote, local_ref, remote_ref))"]
    N011["return specs"]
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
```

## _iter_push_specs(...)

```mermaid
flowchart TD
    N001["_iter_push_specs(...)"]
    N002["specs = []"]
    N003["for segment in _SEGMENT_SPLIT.split(command):     segment = segment.strip()     if '<str>' not in segment:         continue     push_args = _push_args_in_segment(segment)     if push_args is None:         continue     specs.extend(_specs_from_push_args(push_args))"]
    N004["return specs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _rev_parse(...)

```mermaid
flowchart TD
    N001["_rev_parse(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["return result.stdout.strip() or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _commits_for_spec(...)

```mermaid
flowchart TD
    N001["_commits_for_spec(...)"]
    N002["local_sha = _rev_parse(...)"]
    N003["if local_sha is None"]
    N004["return None"]
    N005["remote_sha = _rev_parse(...)"]
    N006["if remote_sha is not None and _ALL_ZEROS_RE.match(remote_sha)"]
    N007["remote_sha = None"]
    N008["if remote_sha is not None"]
    N009["rev_args = ['<str>', f'{remote_sha}<str>{local_sha}']"]
    N010["rev_args = ['<str>', local_sha, '<str>', f'<str>{remote}']"]
    N011["try"]
    N012["result = runner(...)"]
    N013["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N014["return None"]
    N015["if result.returncode != 0"]
    N016["return None"]
    N017["return [line.strip() for line in result.stdout.splitlines() if line.strip()]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N009 --> N011
    N010 --> N011
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N012 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## _is_unsigned(...)

```mermaid
flowchart TD
    N001["_is_unsigned(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return False"]
    N006["if result.returncode != 0"]
    N007["return False"]
    N008["for line in result.stdout.splitlines():     if not line:         break     if line.startswith('<str>'):         return False"]
    N009["return True"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## _deny(...)

```mermaid
flowchart TD
    N001["_deny(...)"]
    N002["shown = join(...)"]
    N003["more = '<str>' if len(unsigned) <= 10 else f'<str>{len(unsigned) - 10}<str>'"]
    N004["return build_deny(f'<str>{len(unsigned)}<str>{shown}{more}<str>{_ACK_MARKER}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
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
    N007["if not _PUSH_MENTION_RE.search(command)"]
    N008["return None"]
    N009["if _ACK_MARKER in command"]
    N010["return None"]
    N011["specs = _iter_push_specs(...)"]
    N012["if not specs"]
    N013["return None"]
    N014["unsigned = []"]
    N015["seen = set(...)"]
    N016["for remote, local_ref, remote_ref in specs:     commits = _commits_for_spec(runner, remote, local_ref, remote_ref)     if not commits:         continue     for sha in commits:         if sha in seen:             continue         seen.add(sha)         if _is_unsigned(runner, sha):             unsigned.append(sha)"]
    N017["if not unsigned"]
    N018["return None"]
    N019["return _deny(unsigned)"]
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
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_event_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
