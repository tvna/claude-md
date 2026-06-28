# AST graph: scripts/backup_non_ascii.py

This file is generated from `scripts/backup_non_ascii.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _parent_number_from_url(...)

```mermaid
flowchart TD
    N001["_parent_number_from_url(...)"]
    N002["if not url"]
    N003["return None"]
    N004["tail = url.rsplit('<str>', 1)[-1]"]
    N005["try"]
    N006["return int(tail)"]
    N007["except ValueError"]
    N008["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
```

## _normalise_issue_or_pr(...)

```mermaid
flowchart TD
    N001["_normalise_issue_or_pr(...)"]
    N002["is_pr = bool(...)"]
    N003["return {'<str>': '<str>' if is_pr else '<str>', '<str>': raw.get('<str>'), '<str>': raw.get('<str>'), '<str>': None, '<str>': raw.get('<str>') or '<str>', '<str>': raw.get('<str>') or '<str>', '<str>': (raw.get('<str>') or {}).get('<str>'), '<str>': raw.get('<str>'), '<str>': raw.get('<str>')}"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _normalise_issue_comment(...)

```mermaid
flowchart TD
    N001["_normalise_issue_comment(...)"]
    N002["return {'<str>': '<str>', '<str>': raw.get('<str>'), '<str>': _parent_number_from_url(raw.get('<str>')), '<str>': raw.get('<str>'), '<str>': '<str>', '<str>': raw.get('<str>') or '<str>', '<str>': (raw.get('<str>') or {}).get('<str>'), '<str>': None, '<str>': raw.get('<str>')}"]
    N001 -->|"start"| N002
```

## _normalise_pr_review_comment(...)

```mermaid
flowchart TD
    N001["_normalise_pr_review_comment(...)"]
    N002["return {'<str>': '<str>', '<str>': raw.get('<str>'), '<str>': _parent_number_from_url(raw.get('<str>')), '<str>': raw.get('<str>'), '<str>': '<str>', '<str>': raw.get('<str>') or '<str>', '<str>': (raw.get('<str>') or {}).get('<str>'), '<str>': None, '<str>': raw.get('<str>')}"]
    N001 -->|"start"| N002
```

## normalise_items(...)

```mermaid
flowchart TD
    N001["normalise_items(...)"]
    N002["items = []"]
    N003["extend(...)"]
    N004["extend(...)"]
    N005["extend(...)"]
    N006["sort(...)"]
    N007["return items"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## build_payload(...)

```mermaid
flowchart TD
    N001["build_payload(...)"]
    N002["return {'<str>': SCHEMA_VERSION, '<str>': captured_at, '<str>': repo, '<str>': items}"]
    N001 -->|"start"| N002
```

## serialise_payload(...)

```mermaid
flowchart TD
    N001["serialise_payload(...)"]
    N002["return json.dumps(payload, sort_keys=True, separators=('<str>', '<str>'), ensure_ascii=False).encode('<str>')"]
    N001 -->|"start"| N002
```

## gzip_bytes(...)

```mermaid
flowchart TD
    N001["gzip_bytes(...)"]
    N002["buf = BytesIO(...)"]
    N003["with gzip.GzipFile(filename='<str>', mode='<str>', fileobj=buf, mtime=mtime) as gz:     gz.write(raw)"]
    N004["return buf.getvalue()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## sha256_hex(...)

```mermaid
flowchart TD
    N001["sha256_hex(...)"]
    N002["return hashlib.sha256(blob).hexdigest()"]
    N001 -->|"start"| N002
```

## _now_iso(...)

```mermaid
flowchart TD
    N001["_now_iso(...)"]
    N002["return datetime.now(UTC).strftime('<str>')"]
    N001 -->|"start"| N002
```

## gh_paginate(...)

```mermaid
flowchart TD
    N001["gh_paginate(...)"]
    N002["if token is None"]
    N003["token = get(...)"]
    N004["return paginate(path, token=token)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
```

## cmd_capture(...)

```mermaid
flowchart TD
    N001["cmd_capture(...)"]
    N002["repo = get(...)"]
    N003["if not repo"]
    N004["print(...)"]
    N005["return 2"]
    N006["token = get(...)"]
    N007["if not token"]
    N008["print(...)"]
    N009["return 2"]
    N010["issues_and_prs = gh_paginate(...)"]
    N011["issue_comments = gh_paginate(...)"]
    N012["pr_review_comments = gh_paginate(...)"]
    N013["items = normalise_items(...)"]
    N014["captured_at = os.environ.get('<str>') or _now_iso()"]
    N015["payload = build_payload(...)"]
    N016["raw = serialise_payload(...)"]
    N017["blob = gzip_bytes(...)"]
    N018["out_path = Path(...)"]
    N019["mkdir(...)"]
    N020["write_bytes(...)"]
    N021["digest = sha256_hex(...)"]
    N022["print(...)"]
    N023["print(...)"]
    N024["print(...)"]
    N025["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N024 --> N025
```

## cmd_sha256(...)

```mermaid
flowchart TD
    N001["cmd_sha256(...)"]
    N002["in_path = Path(...)"]
    N003["blob = read_bytes(...)"]
    N004["print(...)"]
    N005["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_capture = add_parser(...)"]
    N005["add_argument(...)"]
    N006["p_sha = add_parser(...)"]
    N007["add_argument(...)"]
    N008["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = build_parser(...)"]
    N003["args = parse_args(...)"]
    N004["if args.command == 'capture'"]
    N005["return cmd_capture(args)"]
    N006["if args.command == 'sha256'"]
    N007["return cmd_sha256(args)"]
    N008["error(...)"]
    N009["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
