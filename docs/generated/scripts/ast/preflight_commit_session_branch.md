# AST graph: scripts/preflight_commit_session_branch.py

This file is generated from `scripts/preflight_commit_session_branch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _read_authorized_branches(...)

```mermaid
flowchart TD
    N001["_read_authorized_branches(...)"]
    N002["return read_authorized_set(_SESSION_BRANCH_FILE)"]
    N001 -->|"start"| N002
```

## _current_branch(...)

```mermaid
flowchart TD
    N001["_current_branch(...)"]
    N002["try"]
    N003["head = strip(...)"]
    N004["except OSError"]
    N005["return None"]
    N006["if not head.startswith(_HEAD_REF_PREFIX)"]
    N007["return None"]
    N008["branch = strip(...)"]
    N009["return branch or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if os.environ.get(_REMOTE_ENV_VAR, '').lower() != 'true'"]
    N003["return None"]
    N004["if event.get('tool_name') != 'Bash'"]
    N005["return None"]
    N006["command = str(...)"]
    N007["if not _GIT_COMMIT_RE.search(command)"]
    N008["return None"]
    N009["authorized = _read_authorized_branches(...)"]
    N010["if not authorized"]
    N011["return None"]
    N012["current_branch = _current_branch(...)"]
    N013["if not current_branch"]
    N014["return None"]
    N015["if is_authorized(current_branch, authorized)"]
    N016["return None"]
    N017["authorized_list = join(...)"]
    N018["target_hint = sorted(authorized)[0]"]
    N019["return build_deny(f'<str>{authorized_list}<str>{current_branch}<str>{target_hint}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 --> N019
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
