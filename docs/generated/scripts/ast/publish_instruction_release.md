# AST graph: scripts/publish_instruction_release.py

This file is generated from `scripts/publish_instruction_release.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _content_type(...)

```mermaid
flowchart TD
    N001["_content_type(...)"]
    N002["return _CONTENT_TYPES.get(Path(name).suffix, '<str>')"]
    N001 -->|"start"| N002
```

## _create_release(...)

```mermaid
flowchart TD
    N001["_create_release(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>'"]
    N003["payload = {'<str>': tag, '<str>': tag, '<str>': _RELEASE_BODY, '<str>': False, '<str>': False}"]
    N004["(code, resp) = apply_call(...)"]
    N005["if not 200 <= code < 300"]
    N006["raise RuntimeError(f'<str>{code or '<str>'}<str>{resp[:200]}')"]
    N007["try"]
    N008["data = loads(...)"]
    N009["except json.JSONDecodeError"]
    N010["raise RuntimeError(f'<str>{exc}')"]
    N011["if not isinstance(data, dict) or 'id' not in data"]
    N012["raise RuntimeError(f'<str>{resp[:200]}')"]
    N013["return (int(data['<str>']), str(data.get('<str>', '<str>')))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## publish(...)

```mermaid
flowchart TD
    N001["publish(...)"]
    N002["apply_call = apply_call or _github_apply_call"]
    N003["upload_asset = upload_asset or _github_upload_asset"]
    N004["if not asset_paths"]
    N005["raise RuntimeError('<str>')"]
    N006["for path in asset_paths:     if not Path(path).is_file():         raise RuntimeError(f'<str>{path}')"]
    N007["(release_id, html_url) = _create_release(...)"]
    N008["for path in asset_paths:     name = Path(path).name     content = Path(path).read_bytes()     code, resp = upload_asset(repo=repo, release_id=release_id, name=name, content=content, content_type=_content_type(name), token=token)     if not 200 <= code < 300:         raise RuntimeError(f'<str>{name}<str>{code or '<str>'}<str>{resp[:200]}')"]
    N009["return html_url"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _cmd_publish(...)

```mermaid
flowchart TD
    N001["_cmd_publish(...)"]
    N002["token = os.environ.get('<str>') or os.environ.get('<str>') or '<str>'"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["repo = get(...)"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["try"]
    N011["html_url = publish(...)"]
    N012["except RuntimeError"]
    N013["print(...)"]
    N014["return 1"]
    N015["print(...)"]
    N016["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 --> N016
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["publish_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["args = parse_args(...)"]
    N008["if args.cmd == 'publish'"]
    N009["return _cmd_publish(args)"]
    N010["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```
