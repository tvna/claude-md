# AST graph: scripts/ccusage_pin.py

This file is generated from `scripts/ccusage_pin.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## read_flake_text(...)

```mermaid
flowchart TD
    N001["read_flake_text(...)"]
    N002["try"]
    N003["return flake_path.read_text(encoding='<str>')"]
    N004["except OSError"]
    N005["raise CcusagePinError(f'<str>{flake_path}<str>{exc}')"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## ccusage_version(...)

```mermaid
flowchart TD
    N001["ccusage_version(...)"]
    N002["match = search(...)"]
    N003["if match is None"]
    N004["raise CcusagePinError('<str>')"]
    N005["return match.group(1)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _ccusage_native_block(...)

```mermaid
flowchart TD
    N001["_ccusage_native_block(...)"]
    N002["match = search(...)"]
    N003["if match is None"]
    N004["raise CcusagePinError('<str>')"]
    N005["return match.group(1)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _system_entry(...)

```mermaid
flowchart TD
    N001["_system_entry(...)"]
    N002["entry_re = compile(...)"]
    N003["match = search(...)"]
    N004["if match is None"]
    N005["raise CcusagePinError(f'<str>{system}<str>')"]
    N006["return match.group(1)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## sri_to_hex(...)

```mermaid
flowchart TD
    N001["sri_to_hex(...)"]
    N002["if not sri.startswith('sha256-')"]
    N003["raise CcusagePinError(f'<str>{sri!r}')"]
    N004["b64 = sri[len('<str>'):]"]
    N005["try"]
    N006["raw = b64decode(...)"]
    N007["except (binascii.Error, ValueError)"]
    N008["raise CcusagePinError(f'<str>{sri!r}<str>{exc}')"]
    N009["if len(raw) != 32"]
    N010["raise CcusagePinError(f'<str>{sri!r}<str>{len(raw)}<str>')"]
    N011["return raw.hex()"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## resolve(...)

```mermaid
flowchart TD
    N001["resolve(...)"]
    N002["entry = _system_entry(...)"]
    N003["pkg_match = search(...)"]
    N004["hash_match = search(...)"]
    N005["if pkg_match is None"]
    N006["raise CcusagePinError(f'<str>{system}<str>')"]
    N007["if hash_match is None"]
    N008["raise CcusagePinError(f'<str>{system}<str>')"]
    N009["return (ccusage_version(text), pkg_match.group(1), sri_to_hex(hash_match.group(1)))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## _cmd_version(...)

```mermaid
flowchart TD
    N001["_cmd_version(...)"]
    N002["print(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_resolve(...)

```mermaid
flowchart TD
    N001["_cmd_resolve(...)"]
    N002["(version, pkg, sha) = resolve(...)"]
    N003["print(...)"]
    N004["print(...)"]
    N005["print(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_version = add_parser(...)"]
    N005["set_defaults(...)"]
    N006["p_resolve = add_parser(...)"]
    N007["add_argument(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["try"]
    N011["return args.func(args)"]
    N012["except CcusagePinError"]
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
