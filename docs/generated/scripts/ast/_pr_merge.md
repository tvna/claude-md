# AST graph: scripts/_pr_merge.py

This file is generated from `scripts/_pr_merge.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _list_open_prs_by_author(...)

```mermaid
flowchart TD
    N001["_list_open_prs_by_author(...)"]
    N002["results = []"]
    N003["for page in range(1, 11):     url = f'{_API_ROOT}<str>{repo}<str>{page}'     code, body = apply_call(method='<str>', url=url, payload=None, token=token)     if not 200 <= code < 300:         raise RuntimeError(f'<str>{code}<str>{body[:200]}')     try:         data = json.loads(body)     except json.JSONDecodeError as exc:         raise RuntimeError(f'<str>{body[:200]}') from exc     if not isinstance(data, list):         raise RuntimeError(f'<str>{body[:200]}')     for pr in data:         login = pr.get('<str>', {}).get('<str>', '<str>') if isinstance(pr, dict) else '<str>'         if login == author_login:             results.append(pr)     if len(data) < 100:         break"]
    N004["return results"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _poll_pr_mergeability(...)

```mermaid
flowchart TD
    N001["_poll_pr_mergeability(...)"]
    N002["pr = {}"]
    N003["for attempt in range(_MERGE_POLL_ATTEMPTS):     if attempt:         sleeper(_MERGE_POLL_INTERVAL_SECONDS)     pr = _get_pr(repo=repo, number=number, token=token, apply_call=apply_call)     if pr.get('<str>') is not None:         break"]
    N004["return pr"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _merge_pr_if_clean(...)

```mermaid
flowchart TD
    N001["_merge_pr_if_clean(...)"]
    N002["pr = _poll_pr_mergeability(...)"]
    N003["state = lower(...)"]
    N004["if state != 'clean'"]
    N005["print(...)"]
    N006["return False"]
    N007["head_sha = pr.get('<str>', {}).get('<str>', '<str>') if isinstance(pr.get('<str>'), dict) else '<str>'"]
    N008["if not head_sha"]
    N009["raise RuntimeError(f'<str>{number}<str>')"]
    N010["if not _merge_pr(repo=repo, number=number, sha=head_sha, merge_method='squash', token=token, apply_call=apply_call)"]
    N011["print(...)"]
    N012["return False"]
    N013["print(...)"]
    N014["if head_ref"]
    N015["try"]
    N016["_delete_branch(...)"]
    N017["except RuntimeError"]
    N018["print(...)"]
    N019["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N016 --> N019
    N018 --> N019
    N014 -->|"false"| N019
```
