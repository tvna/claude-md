# AST graph: scripts/bot_pr_automerge.py

This file is generated from `scripts/bot_pr_automerge.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _cmd_merge(...)

```mermaid
flowchart TD
    N001["_cmd_merge(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["repo = get(...)"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["author_login = os.environ.get('<str>') or _DEFAULT_BOT_AUTHOR_LOGIN"]
    N011["prs = _list_open_prs_by_author(...)"]
    N012["if not prs"]
    N013["print(...)"]
    N014["return 0"]
    N015["merged = 0"]
    N016["for pr in prs:     number = int(pr['<str>'])     head_ref = pr.get('<str>', {}).get('<str>', '<str>') if isinstance(pr.get('<str>'), dict) else '<str>'     if _merge_pr_if_clean(repo=repo, number=number, head_ref=head_ref, token=token):         merged += 1"]
    N017["print(...)"]
    N018["return 0"]
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
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["args = parse_args(...)"]
    N006["if args.cmd == 'merge'"]
    N007["return _cmd_merge(args)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```
