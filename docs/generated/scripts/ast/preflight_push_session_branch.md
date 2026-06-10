# AST graph: scripts/preflight_push_session_branch.py

This file is generated from `scripts/preflight_push_session_branch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _read_authorized_branches(...)

```mermaid
flowchart TD
    N001["_read_authorized_branches(...)"]
    N002["return read_authorized_set(_SESSION_BRANCH_FILE)"]
    N001 -->|"start"| N002
```

## _extract_push_remote_ref(...)

```mermaid
flowchart TD
    N001["_extract_push_remote_ref(...)"]
    N002["m = search(...)"]
    N003["if not m"]
    N004["return None"]
    N005["try"]
    N006["tokens = split(...)"]
    N007["except ValueError"]
    N008["return None"]
    N009["positionals = []"]
    N010["i = 0"]
    N011["end_of_opts = False"]
    N012["while i < len(tokens):
    tok = tokens[i]
    if not end_of_opts and tok == '<str>':
        end_of_opts = True
        i += 1
        continue
    if not end_of_opts and tok.startswith('<str>'):
        if '<str>' in tok or tok in _FLAGS_NO_VALUE:
            i += 1
        elif tok in _FLAGS_WITH_VALUE:
            i += 2
        else:
            i += 1
        continue
    positionals.append(tok)
    i += 1"]
    N013["if len(positionals) < 2"]
    N014["return None"]
    N015["refspec = positionals[1]"]
    N016["if refspec.startswith('+')"]
    N017["refspec = refspec[1:]"]
    N018["if ':' in refspec"]
    N019["return refspec.split('<str>', 1)[1]"]
    N020["return refspec"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
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
    N007["if not _GIT_PUSH_RE.search(command)"]
    N008["return None"]
    N009["authorized = _read_authorized_branches(...)"]
    N010["if not authorized"]
    N011["return None"]
    N012["remote_ref = _extract_push_remote_ref(...)"]
    N013["if not remote_ref"]
    N014["return None"]
    N015["if remote_ref == 'HEAD' or is_authorized(remote_ref, authorized)"]
    N016["return None"]
    N017["authorized_list = join(...)"]
    N018["target_hint = sorted(authorized)[0]"]
    N019["return build_deny(f'<str>{authorized_list}<str>{remote_ref}<str>{target_hint}<str>')"]
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
