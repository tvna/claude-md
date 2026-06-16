# AST graph: scripts/doc_graph_viz.py

This file is generated from `scripts/doc_graph_viz.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _build_content(...)

```mermaid
flowchart TD
    N001["_build_content(...)"]
    N002["graph = load_graph(...)"]
    N003["diagram = render_mermaid(...)"]
    N004["node_count = len(...)"]
    N005["edge_count = len(...)"]
    N006["blocking = sum(...)"]
    N007["advisory = edge_count - blocking"]
    N008["return f'<str>{graph_path}<str>{node_count}<str>{edge_count}<str>{blocking}<str>{advisory}<str>{diagram}<str>{_LEGEND}'"]
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
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["graph_path = Path(...)"]
    N008["if not graph_path.exists()"]
    N009["print(...)"]
    N010["return 1"]
    N011["try"]
    N012["content = _build_content(...)"]
    N013["except GraphValidationError"]
    N014["print(...)"]
    N015["return 1"]
    N016["if args.subcommand == 'preview'"]
    N017["print(...)"]
    N018["return 0"]
    N019["out_path = Path(...)"]
    N020["mkdir(...)"]
    N021["write_text(...)"]
    N022["graph = load_graph(...)"]
    N023["print(...)"]
    N024["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
```
