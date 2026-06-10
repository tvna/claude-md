# AST graph: scripts/gen_mcp_json.py

This file is generated from `scripts/gen_mcp_json.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _server_entry(...)

```mermaid
flowchart TD
    N001["_server_entry(...)"]
    N002["transport = get(...)"]
    N003["if transport in ('http', 'sse')"]
    N004["url = get(...)"]
    N005["if not isinstance(url, str) or not url"]
    N006["raise ValueError(f\"<str>{server.get('<str>')!r}<str>{transport}<str>\")"]
    N007["return {'<str>': transport, '<str>': url}"]
    N008["if transport == 'stdio'"]
    N009["command = get(...)"]
    N010["if not isinstance(command, str) or not command"]
    N011["raise ValueError(f\"<str>{server.get('<str>')!r}<str>\")"]
    N012["entry = {'<str>': '<str>', '<str>': command}"]
    N013["args = get(...)"]
    N014["if args is not None"]
    N015["entry['<str>'] = args"]
    N016["return entry"]
    N017["raise ValueError(f\"<str>{server.get('<str>')!r}<str>{transport!r}\")"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N003 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
    N008 -->|"false"| N017
```

## render_mcp_config(...)

```mermaid
flowchart TD
    N001["render_mcp_config(...)"]
    N002["servers = (apm_data.get('<str>') or {}).get('<str>') or []"]
    N003["mcp_servers = {}"]
    N004["for server in servers:
    if not isinstance(server, dict):
        raise ValueError(f'<str>{type(server).__name__}')
    name = server.get('<str>')
    if not isinstance(name, str) or not name:
        raise ValueError('<str>')
    mcp_servers[name] = _server_entry(server)"]
    N005["return {'<str>': mcp_servers}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _load_apm(...)

```mermaid
flowchart TD
    N001["_load_apm(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except OSError"]
    N005["print(...)"]
    N006["raise SystemExit(2)"]
    N007["try"]
    N008["data = safe_load(...)"]
    N009["except yaml.YAMLError"]
    N010["print(...)"]
    N011["raise SystemExit(2)"]
    N012["if not isinstance(data, dict)"]
    N013["print(...)"]
    N014["raise SystemExit(2)"]
    N015["return data"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
```

## _serialise(...)

```mermaid
flowchart TD
    N001["_serialise(...)"]
    N002["return json.dumps(config, indent=2, sort_keys=True) + '<str>'"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["try"]
    N006["config = render_mcp_config(...)"]
    N007["except ValueError"]
    N008["print(...)"]
    N009["return 2"]
    N010["rendered = _serialise(...)"]
    N011["if args.check"]
    N012["try"]
    N013["current = read_text(...)"]
    N014["except OSError"]
    N015["print(...)"]
    N016["return 1"]
    N017["if current != rendered"]
    N018["print(...)"]
    N019["return 1"]
    N020["return 0"]
    N021["write_text(...)"]
    N022["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 -->|"try"| N013
    N012 -->|"raises"| N014
    N014 --> N015
    N015 --> N016
    N013 --> N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N020
    N011 -->|"false"| N021
    N021 --> N022
```
