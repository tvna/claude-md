# AST graph: scripts/preflight_cache.py

This file is generated from `scripts/preflight_cache.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _git_dir(...)

```mermaid
flowchart TD
    N001["_git_dir(...)"]
    N002["out = strip(...)"]
    N003["git_dir = Path(...)"]
    N004["if not git_dir.is_absolute()"]
    N005["git_dir = resolve(...)"]
    N006["return git_dir"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
```

## cache_path(...)

```mermaid
flowchart TD
    N001["cache_path(...)"]
    N002["return _git_dir(repo_root) / _CACHE_BASENAME"]
    N001 -->|"start"| N002
```

## _tracked_input_files(...)

```mermaid
flowchart TD
    N001["_tracked_input_files(...)"]
    N002["out = run_git(['<str>', '<str>', '<str>', *INPUT_PATHSPECS], cwd=repo_root, check=True).stdout"]
    N003["rels = [chunk for chunk in out.split('<str>') if chunk]"]
    N004["files = [repo_root / rel for rel in rels]"]
    N005["return sorted((p for p in files if p.is_file()), key=lambda p: p.as_posix())"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## compute_fingerprint(...)

```mermaid
flowchart TD
    N001["compute_fingerprint(...)"]
    N002["digest = sha256(...)"]
    N003["for path in _tracked_input_files(repo_root):     rel = path.relative_to(repo_root).as_posix()     digest.update(rel.encode('<str>'))     digest.update(b'\x00')     digest.update(hashlib.sha256(path.read_bytes()).digest())     digest.update(b'\x00')"]
    N004["update(...)"]
    N005["for token in extra:     digest.update(token.encode('<str>'))     digest.update(b'\x00')"]
    N006["return digest.hexdigest()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## load(...)

```mermaid
flowchart TD
    N001["load(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except OSError"]
    N005["return None"]
    N006["try"]
    N007["data = loads(...)"]
    N008["except json.JSONDecodeError"]
    N009["return None"]
    N010["return data if isinstance(data, dict) else None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
```

## is_fresh(...)

```mermaid
flowchart TD
    N001["is_fresh(...)"]
    N002["if cache is None"]
    N003["return False"]
    N004["return cache.get('<str>') == fingerprint and cache.get('<str>') == '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## record(...)

```mermaid
flowchart TD
    N001["record(...)"]
    N002["payload = {'<str>': fingerprint, '<str>': '<str>', '<str>': datetime.now(UTC).strftime('<str>')}"]
    N003["try"]
    N004["write_text(...)"]
    N005["except OSError"]
    N006["print(...)"]
    N007["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N006 --> N007
```

## cache_disabled(...)

```mermaid
flowchart TD
    N001["cache_disabled(...)"]
    N002["return environ.get(_ENV_DISABLE, '<str>') == '<str>'"]
    N001 -->|"start"| N002
```

## _format_status(...)

```mermaid
flowchart TD
    N001["_format_status(...)"]
    N002["if cache is None"]
    N003["return '<str>'"]
    N004["if is_fresh(cache, fingerprint)"]
    N005["ts = get(...)"]
    N006["return f'<str>{ts}'"]
    N007["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["if args.command == 'status'"]
    N006["try"]
    N007["fingerprint = compute_fingerprint(...)"]
    N008["except (OSError, subprocess.SubprocessError)"]
    N009["print(...)"]
    N010["return 0"]
    N011["cache = load(...)"]
    N012["print(...)"]
    N013["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N009 --> N010
    N007 --> N011
    N011 --> N012
    N012 --> N013
    N005 -->|"false"| N013
```
