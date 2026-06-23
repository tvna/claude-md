# AST graph: scripts/post_issue_comment.py

This file is generated from `scripts/post_issue_comment.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _post_comment(...)

```mermaid
flowchart TD
    N001["_post_comment(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>{issue_number}<str>'"]
    N003["(code, resp) = apply_call(...)"]
    N004["if not 200 <= code < 300"]
    N005["raise RuntimeError(f'<str>{code}<str>{resp[:200]}')"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _cmd_create(...)

```mermaid
flowchart TD
    N001["_cmd_create(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["repo = get(...)"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["if args.body_file"]
    N011["body = read_text(...)"]
    N012["if args.body is not None"]
    N013["body = args.body"]
    N014["print(...)"]
    N015["return 1"]
    N016["try"]
    N017["_post_comment(...)"]
    N018["except RuntimeError"]
    N019["print(...)"]
    N020["return 1"]
    N021["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N011 --> N016
    N013 --> N016
    N016 -->|"try"| N017
    N016 -->|"raises"| N018
    N018 --> N019
    N019 --> N020
    N017 --> N021
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["create_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["args = parse_args(...)"]
    N009["if args.cmd == 'create'"]
    N010["return _cmd_create(args)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```
