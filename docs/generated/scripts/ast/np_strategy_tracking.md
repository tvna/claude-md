# AST graph: scripts/np_strategy_tracking.py

This file is generated from `scripts/np_strategy_tracking.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## plan_label_swap(...)

```mermaid
flowchart TD
    N001["plan_label_swap(...)"]
    N002["type_labels = [name for name in labels if name.startswith(TYPE_PREFIX)]"]
    N003["non_type = [name for name in labels if not name.startswith(TYPE_PREFIX)]"]
    N004["removed = [name for name in type_labels if name != TRACKING_LABEL]"]
    N005["already_tracking = type_labels == [TRACKING_LABEL]"]
    N006["result = []"]
    N007["for name in [*non_type, TRACKING_LABEL]:
    if name not in result:
        result.append(name)"]
    N008["return {'<str>': already_tracking, '<str>': removed, '<str>': result}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## format_rationale(...)

```mermaid
flowchart TD
    N001["format_rationale(...)"]
    N002["pr_list = '<str>'.join((f'<str>{p}' for p in prs)) if prs else '<str>'"]
    N003["swapped = '<str>'.join((f'<str>{name}<str>' for name in removed)) if removed else '<str>'"]
    N004["text = f'<str>{TRACKING_LABEL}<str>{issue}<str>{pr_list}<str>{swapped}<str>{issue}<str>'"]
    N005["if reason"]
    N006["text += f'<str>{reason}'"]
    N007["return text"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## fetch_labels(...)

```mermaid
flowchart TD
    N001["fetch_labels(...)"]
    N002["(code, body) = apply_call(...)"]
    N003["if not 200 <= code < 300"]
    N004["raise RuntimeError(f'<str>{issue}<str>{code}<str>')"]
    N005["data = loads(...)"]
    N006["raw = data.get('<str>', []) if isinstance(data, dict) else []"]
    N007["names = []"]
    N008["for entry in raw:
    if isinstance(entry, dict) and isinstance(entry.get('<str>'), str):
        names.append(entry['<str>'])
    elif isinstance(entry, str):
        names.append(entry)"]
    N009["return names"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## put_labels(...)

```mermaid
flowchart TD
    N001["put_labels(...)"]
    N002["(code, _) = apply_call(...)"]
    N003["if not 200 <= code < 300"]
    N004["raise RuntimeError(f'<str>{issue}<str>{code}<str>')"]
    N005["return code"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## post_comment(...)

```mermaid
flowchart TD
    N001["post_comment(...)"]
    N002["(code, _) = apply_call(...)"]
    N003["if not 200 <= code < 300"]
    N004["raise RuntimeError(f'<str>{issue}<str>{code}<str>')"]
    N005["return code"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## run(...)

```mermaid
flowchart TD
    N001["run(...)"]
    N002["labels = fetch_labels(...)"]
    N003["plan = plan_label_swap(...)"]
    N004["rationale = format_rationale(...)"]
    N005["if plan['already_tracking']"]
    N006["print(...)"]
    N007["return 0"]
    N008["print(...)"]
    N009["print(...)"]
    N010["print(...)"]
    N011["if mode == 'plan'"]
    N012["print(...)"]
    N013["return 0"]
    N014["put_labels(...)"]
    N015["post_comment(...)"]
    N016["print(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
```

## parse_prs(...)

```mermaid
flowchart TD
    N001["parse_prs(...)"]
    N002["if not raw"]
    N003["return []"]
    N004["out = []"]
    N005["for token in raw.replace('<str>', '<str>').split():
    out.append(int(token.lstrip('<str>')))"]
    N006["return out"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["for name in ('<str>', '<str>'):
    p = sub.add_parser(name)
    p.add_argument('<str>', default=os.environ.get('<str>', '<str>'))
    p.add_argument('<str>', type=int, required=True)
    p.add_argument('<str>', default='<str>', help='<str>')
    p.add_argument('<str>', default=None, help='<str>')"]
    N005["args = parse_args(...)"]
    N006["if not args.repo"]
    N007["print(...)"]
    N008["return 1"]
    N009["token = os.environ.get('<str>') or os.environ.get('<str>') or '<str>'"]
    N010["if not token"]
    N011["print(...)"]
    N012["return 1"]
    N013["try"]
    N014["return run(mode=args.mode, repo=args.repo, issue=args.issue, prs=parse_prs(args.prs), reason=args.reason, token=token)"]
    N015["except (RuntimeError, ValueError, json.JSONDecodeError)"]
    N016["print(...)"]
    N017["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N016 --> N017
```
