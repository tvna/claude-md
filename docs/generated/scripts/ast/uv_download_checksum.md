# AST graph: scripts/uv_download_checksum.py

This file is generated from `scripts/uv_download_checksum.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## flake_uv_sha256_hex(...)

```mermaid
flowchart TD
    N001["flake_uv_sha256_hex(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["raise ValueError(f'<str>{flake_path}<str>{exc}')"]
    N006["pattern = compile(...)"]
    N007["match = search(...)"]
    N008["if match is None"]
    N009["raise ValueError(f'<str>{target!r}<str>{flake_path}')"]
    N010["try"]
    N011["raw = b64decode(...)"]
    N012["except ValueError"]
    N013["raise ValueError(f'<str>{target!r}<str>{exc}')"]
    N014["if len(raw) != 32"]
    N015["raise ValueError(f'<str>{target!r}<str>')"]
    N016["return raw.hex()"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N011 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
```

## file_sha256_hex(...)

```mermaid
flowchart TD
    N001["file_sha256_hex(...)"]
    N002["digest = sha256(...)"]
    N003["try"]
    N004["with file_path.open('<str>') as handle:     for chunk in iter(lambda: handle.read(1024 * 1024), b''):         digest.update(chunk)"]
    N005["except OSError"]
    N006["raise ValueError(f'<str>{file_path}<str>{exc}')"]
    N007["return digest.hexdigest()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["expected = flake_uv_sha256_hex(...)"]
    N003["actual = file_sha256_hex(...)"]
    N004["if actual != expected"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["try"]
    N011["return args.func(args)"]
    N012["except ValueError"]
    N013["print(...)"]
    N014["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
```
