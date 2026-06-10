# AST graph: scripts/github_api.py

This file is generated from `scripts/github_api.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _filter_fields(...)

```mermaid
flowchart TD
    N001["_filter_fields(...)"]
    N002["if not fields"]
    N003["return data"]
    N004["if isinstance(data, dict)"]
    N005["return {k: v for k, v in data.items() if k in fields}"]
    N006["if isinstance(data, list)"]
    N007["return [{k: v for k, v in item.items() if k in fields} if isinstance(item, dict) else item for item in data]"]
    N008["return data"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["import argparse"]
    N003["parser = ArgumentParser(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["args = parse_args(...)"]
    N010["token = args.token or os.environ.get('<str>', '<str>')"]
    N011["if not token"]
    N012["print(...)"]
    N013["return 2"]
    N014["if not args.url.startswith('https://api.github.com/')"]
    N015["print(...)"]
    N016["return 2"]
    N017["payload = None"]
    N018["if args.payload"]
    N019["try"]
    N020["payload = loads(...)"]
    N021["except json.JSONDecodeError"]
    N022["print(...)"]
    N023["return 2"]
    N024["(code, body) = apply_call(...)"]
    N025["if not 200 <= code < 300"]
    N026["print(...)"]
    N027["return 1"]
    N028["fields = [f.strip() for f in args.fields.split('<str>') if f.strip()]"]
    N029["if fields"]
    N030["try"]
    N031["data = loads(...)"]
    N032["except json.JSONDecodeError"]
    N033["write(...)"]
    N034["return 0"]
    N035["write(...)"]
    N036["write(...)"]
    N037["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N019 -->|"try"| N020
    N019 -->|"raises"| N021
    N021 --> N022
    N022 --> N023
    N020 --> N024
    N018 -->|"false"| N024
    N024 --> N025
    N025 -->|"true"| N026
    N026 --> N027
    N025 -->|"false"| N028
    N028 --> N029
    N029 -->|"true"| N030
    N030 -->|"try"| N031
    N030 -->|"raises"| N032
    N032 --> N033
    N033 --> N034
    N031 --> N035
    N029 -->|"false"| N036
    N035 --> N037
    N036 --> N037
```
