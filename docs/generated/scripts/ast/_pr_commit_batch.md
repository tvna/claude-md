# AST graph: scripts/_pr_commit_batch.py

This file is generated from `scripts/_pr_commit_batch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _create_commit_on_branch(...)

```mermaid
flowchart TD
    N001["_create_commit_on_branch(...)"]
    N002["message = {'<str>': headline}"]
    N003["if body"]
    N004["message['<str>'] = body"]
    N005["file_changes = {'<str>': additions}"]
    N006["if deletions"]
    N007["file_changes['<str>'] = deletions"]
    N008["variables = {'<str>': {'<str>': {'<str>': repo, '<str>': branch}, '<str>': message, '<str>': expected_head_oid, '<str>': file_changes}}"]
    N009["(code, response) = graphql_call(...)"]
    N010["if not 200 <= code < 300"]
    N011["raise RuntimeError(f'<str>{code}')"]
    N012["if 'errors' in response"]
    N013["raise RuntimeError(f'<str>{response['<str>']}')"]
    N014["try"]
    N015["oid = response['<str>']['<str>']['<str>']['<str>']"]
    N016["except (KeyError, TypeError)"]
    N017["raise RuntimeError(f'<str>{str(response)[:200]}')"]
    N018["if not isinstance(oid, str) or not oid"]
    N019["raise RuntimeError(f'<str>{str(response)[:200]}')"]
    N020["return oid"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"try"| N015
    N014 -->|"raises"| N016
    N016 --> N017
    N015 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
```

## _batch_additions(...)

```mermaid
flowchart TD
    N001["_batch_additions(...)"]
    N002["batches = []"]
    N003["current = []"]
    N004["size = 0"]
    N005["for item in additions:     item_size = len(item['<str>'])     if current and (len(current) >= max_files or size + item_size > max_bytes):         batches.append(current)         current = []         size = 0     current.append(item)     size += item_size"]
    N006["if current"]
    N007["append(...)"]
    N008["return batches"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```

## _create_commits_in_batches(...)

```mermaid
flowchart TD
    N001["_create_commits_in_batches(...)"]
    N002["batches = _batch_additions(additions, max_files=max_files, max_bytes=max_bytes) or [[]]"]
    N003["total = len(...)"]
    N004["head_oid = start_oid"]
    N005["for index, batch in enumerate(batches, start=1):     commit_headline = headline if total == 1 else f'{headline}<str>{index}<str>{total}<str>'     head_oid = _create_commit_on_branch(repo=repo, branch=branch, expected_head_oid=head_oid, headline=commit_headline, body=body, additions=batch, deletions=deletions if index == 1 else None, token=token, graphql_call=graphql_call)"]
    N006["return head_oid"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```
