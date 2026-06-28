# AST graph: scripts/gate_pr_body_retro_issue_link.py

This file is generated from `scripts/gate_pr_body_retro_issue_link.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## fetch_issue_title(...)

```mermaid
flowchart TD
    N001["fetch_issue_title(...)"]
    N002["kwargs = {}"]
    N003["if opener is not None"]
    N004["kwargs['<str>'] = opener"]
    N005["if sleeper is not None"]
    N006["kwargs['<str>'] = sleeper"]
    N007["try"]
    N008["(status, body) = apply_call(...)"]
    N009["except Exception"]
    N010["return None"]
    N011["if not 200 <= status < 300"]
    N012["return None"]
    N013["try"]
    N014["data = loads(...)"]
    N015["except (json.JSONDecodeError, ValueError)"]
    N016["return None"]
    N017["title = data.get('<str>') if isinstance(data, dict) else None"]
    N018["return title if isinstance(title, str) else None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
    N017 --> N018
```

## _deny_reason(...)

```mermaid
flowchart TD
    N001["_deny_reason(...)"]
    N002["joined = join(...)"]
    N003["return f'<str>{_SCRIPT_NAME}<str>{tool_name}<str>{joined}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["body = get(...)"]
    N005["if not isinstance(body, str)"]
    N006["return None"]
    N007["title = get(...)"]
    N008["if isinstance(title, str) and is_retro_pr(title)"]
    N009["return None"]
    N010["refs = extract_refs(...)"]
    N011["if not refs"]
    N012["return None"]
    N013["owner = get(...)"]
    N014["repo = get(...)"]
    N015["if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo)"]
    N016["return None"]
    N017["token = token_getter(...)"]
    N018["if not token"]
    N019["return None"]
    N020["retro_numbers = []"]
    N021["for number in refs:     issue_title = title_getter(owner, repo, number)     if issue_title is None:         return None     if is_retro_issue_title(issue_title):         retro_numbers.append(number)"]
    N022["if not retro_numbers"]
    N023["return None"]
    N024["return build_deny(_deny_reason(retro_numbers, tool_name))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
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
    N005["return run_tool_hook(_SCRIPT_NAME, lambda tool_name, tool_input: decide(tool_name, tool_input, token_getter=_token_getter, title_getter=_title_getter))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
