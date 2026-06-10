# AST graph: scripts/verify_dependabot_author.py

This file is generated from `scripts/verify_dependabot_author.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## is_violation(...)

```mermaid
flowchart TD
    N001["is_violation(...)"]
    N002["if not head_ref.startswith(_DEPENDABOT_PREFIX)"]
    N003["return False"]
    N004["return author not in _TRUSTED_BOT_LOGINS"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["head_ref = args.head_ref or '<str>'"]
    N003["author = args.author or '<str>'"]
    N004["if is_violation(head_ref, author)"]
    N005["print(...)"]
    N006["return 1"]
    N007["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```
