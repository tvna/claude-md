# AST graph: scripts/scan_allowlist_parser_parity.py

This file is generated from `scripts/scan_allowlist_parser_parity.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## bash_resolve_hosts(...)

```mermaid
flowchart TD
    N001["bash_resolve_hosts(...)"]
    N002["bash = which(...)"]
    N003["if bash is None"]
    N004["raise RuntimeError('<str>')"]
    N005["script = f'<str>{shlex.quote(str(lib))}<str>{shlex.quote(str(allowlist))}'"]
    N006["completed = run(...)"]
    N007["return {line for line in completed.stdout.split() if line}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["lib = joinpath(...)"]
    N003["if not lib.is_file()"]
    N004["return [f'<str>{lib}<str>']"]
    N005["network_dir = joinpath(...)"]
    N006["if not network_dir.is_dir()"]
    N007["return [f'<str>{network_dir}<str>']"]
    N008["files = sorted(...)"]
    N009["if not files"]
    N010["return [f'<str>{ALLOWLIST_GLOB}<str>{network_dir}<str>']"]
    N011["errors = []"]
    N012["for path in files:     try:         rel: Path | str = path.relative_to(repo_root)     except ValueError:         rel = path     python_hosts = resolve_hosts(path)     try:         bash_hosts = bash_resolve_hosts(path, lib)     except subprocess.CalledProcessError as exc:         errors.append(f'<str>{rel}<str>{rel}<str>{exc.stderr.strip()}')         continue     if python_hosts != bash_hosts:         python_only = '<str>'.join(sorted(python_hosts - bash_hosts)) or '<str>'         bash_only = '<str>'.join(sorted(bash_hosts - python_hosts)) or '<str>'         errors.append(f'<str>{rel}<str>{rel}<str>{python_only}<str>{bash_only}<str>')"]
    N013["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 --> N013
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["errors = verify(...)"]
    N004["for err in errors:     print(err, file=sys.stderr)"]
    N005["if errors"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
