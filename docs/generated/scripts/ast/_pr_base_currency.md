# AST graph: scripts/_pr_base_currency.py

This file is generated from `scripts/_pr_base_currency.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _get_file_blob_sha(...)

```mermaid
flowchart TD
    N001["_get_file_blob_sha(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>{path}<str>{ref}'"]
    N003["(code, body) = apply_call(...)"]
    N004["if code == 404"]
    N005["return None"]
    N006["if not 200 <= code < 300"]
    N007["raise RuntimeError(f'<str>{path}<str>{ref}<str>{code}<str>{body[:200]}')"]
    N008["try"]
    N009["data = loads(...)"]
    N010["except json.JSONDecodeError"]
    N011["raise RuntimeError(f'<str>{path}<str>{ref}<str>{body[:200]}')"]
    N012["sha = data.get('<str>') if isinstance(data, dict) else None"]
    N013["if not isinstance(sha, str) or not sha"]
    N014["raise RuntimeError(f'<str>{path}<str>{ref}<str>{body[:200]}')"]
    N015["return sha"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## _git_base_resolvable(...)

```mermaid
flowchart TD
    N001["_git_base_resolvable(...)"]
    N002["return run_git(['<str>', '<str>', '<str>', base]).returncode == 0"]
    N001 -->|"start"| N002
```

## _git_blob_sha(...)

```mermaid
flowchart TD
    N001["_git_blob_sha(...)"]
    N002["result = run_git(...)"]
    N003["if result.returncode != 0"]
    N004["return None"]
    N005["return result.stdout.strip() or None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## verify_base_currency(...)

```mermaid
flowchart TD
    N001["verify_base_currency(...)"]
    N002["if not base_resolvable(base)"]
    N003["return"]
    N004["stale = []"]
    N005["for path in [p for p, _ in additions] + deletions:     remote_sha = _get_file_blob_sha(repo=repo, path=path, ref=base, token=token, apply_call=apply_call)     if local_blob_sha(base, path) != remote_sha:         stale.append(path)"]
    N006["if stale"]
    N007["raise RuntimeError('<str>' + '<str>'.join(sorted(stale)) + f'<str>{base}<str>' + f'{base}<str>' + f'<str>{base}<str>' + '<str>')"]
    N008["end"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```
