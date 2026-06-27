# AST graph: scripts/gate_retro_close_keyword_commit.py

This file is generated from `scripts/gate_retro_close_keyword_commit.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _commit_message_values(...)

```mermaid
flowchart TD
    N001["_commit_message_values(...)"]
    N002["try"]
    N003["tokens = split(...)"]
    N004["except ValueError"]
    N005["return []"]
    N006["n = len(...)"]
    N007["out = []"]
    N008["i = 0"]
    N009["while i < n:     if tokens[i].lstrip(_GROUP_PREFIX) != '<str>' and (not tokens[i].endswith('<str>')):         i += 1         continue     j = i + 1     while j < n and tokens[j].startswith('<str>'):         j += 2 if tokens[j] in _GIT_VALUE_OPTS else 1     if j < n and tokens[j].rstrip(_GROUP_SUFFIX) == '<str>':         k = j + 1         invocation: list[str] = []         while k < n and tokens[k] not in _SHELL_OPS:             invocation.append(tokens[k])             k += 1         out.extend(_message_values(invocation))         i = k         continue     i = j + 1"]
    N010["return out"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## _message_values(...)

```mermaid
flowchart TD
    N001["_message_values(...)"]
    N002["values = []"]
    N003["i = 0"]
    N004["n = len(...)"]
    N005["while i < n:     tok = tokens[i]     if tok in ('<str>', '<str>'):         if i + 1 < n:             values.append(tokens[i + 1])             i += 2             continue     elif tok.startswith('<str>'):         values.append(tok[len('<str>'):])     elif (match := _MSG_FLAG_RE.fullmatch(tok)) is not None:         attached = match.group(1)         if attached:             values.append(attached)         elif i + 1 < n:             values.append(tokens[i + 1])             i += 2             continue     i += 1"]
    N006["return values"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _closing_refs(...)

```mermaid
flowchart TD
    N001["_closing_refs(...)"]
    N002["message = join(...)"]
    N003["found = {int(m.group(1)) for m in _CLOSING_REF_RE.finditer(message)}"]
    N004["return sorted(found)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _detect_repo(...)

```mermaid
flowchart TD
    N001["_detect_repo(...)"]
    N002["repo = get(...)"]
    N003["if repo and _OWNER_REPO_RE.match(repo)"]
    N004["return repo"]
    N005["try"]
    N006["result = run(...)"]
    N007["except (OSError, subprocess.SubprocessError)"]
    N008["return None"]
    N009["if result.returncode != 0"]
    N010["return None"]
    N011["match = search(...)"]
    N012["return match.group(1) if match else None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
```

## _deny_reason(...)

```mermaid
flowchart TD
    N001["_deny_reason(...)"]
    N002["joined = join(...)"]
    N003["return f'<str>{_SCRIPT_NAME}<str>{joined}<str>{_ACK_MARKER}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != 'Bash'"]
    N003["return None"]
    N004["command = str(...)"]
    N005["if not command.strip()"]
    N006["return None"]
    N007["if _ACK_MARKER in command"]
    N008["return None"]
    N009["if not token_getter()"]
    N010["return None"]
    N011["refs = _closing_refs(...)"]
    N012["if not refs"]
    N013["return None"]
    N014["repo = repo_getter(...)"]
    N015["if not repo or '/' not in repo"]
    N016["return None"]
    N017["(owner, _, name) = partition(...)"]
    N018["if not (owner and name)"]
    N019["return None"]
    N020["retro_numbers = []"]
    N021["for number in refs:     title = title_getter(owner, name, number)     if title is None:         return None     if is_retro_issue_title(title):         retro_numbers.append(number)"]
    N022["if not retro_numbers"]
    N023["return None"]
    N024["return build_deny(_deny_reason(retro_numbers))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
    N021 --> N022
    N022 -->|"true"| N023
    N022 -->|"false"| N024
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["def _token_getter() -> str | None:     return os.environ.get('<str>') or os.environ.get('<str>')"]
    N004["def _title_getter(owner: str, repo: str, number: int) -> str | None:     token = _token_getter()     if not token:         return None     return fetch_issue_title(owner, repo, number, token=token)"]
    N005["return run_event_hook(_SCRIPT_NAME, lambda event: decide(event, repo_getter=_detect_repo, token_getter=_token_getter, title_getter=_title_getter), auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
