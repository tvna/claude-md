# AST graph: scripts/_trusted_bots.py

This file is generated from `scripts/_trusted_bots.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load(...)

```mermaid
flowchart TD
    N001["_load(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["print(...)"]
    N006["return (_DEFAULT_GENERAL, _DEFAULT_NON_ASCII_SKIP)"]
    N007["try"]
    N008["import tomllib"]
    N009["data = loads(...)"]
    N010["except Exception"]
    N011["print(...)"]
    N012["return (_DEFAULT_GENERAL, _DEFAULT_NON_ASCII_SKIP)"]
    N013["general = frozenset(...)"]
    N014["non_ascii_skip = frozenset(...)"]
    N015["return (general or _DEFAULT_GENERAL, non_ascii_skip or _DEFAULT_NON_ASCII_SKIP)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 -->|"try"| N008
    N008 --> N009
    N007 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 --> N014
    N014 --> N015
```
