# AST graph: scripts/issue_link.py

This file is generated from `scripts/issue_link.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## strip_html_comments(...)

```mermaid
flowchart TD
    N001["strip_html_comments(...)"]
    N002["return _shared_strip_html_comments(body)"]
    N001 -->|"start"| N002
```

## extract_refs(...)

```mermaid
flowchart TD
    N001["extract_refs(...)"]
    N002["found = {int(m.group(1)) for m in _REF_LINE.finditer(body)}"]
    N003["return sorted(found)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## classify_refs(...)

```mermaid
flowchart TD
    N001["classify_refs(...)"]
    N002["return _shared_classify_refs(body)"]
    N001 -->|"start"| N002
```

## body_has_partial_marker(...)

```mermaid
flowchart TD
    N001["body_has_partial_marker(...)"]
    N002["return _shared_body_has_partial_marker(raw_body)"]
    N001 -->|"start"| N002
```

## verify_ref_exists(...)

```mermaid
flowchart TD
    N001["verify_ref_exists(...)"]
    N002["if runner is None"]
    N003["runner = subprocess.run"]
    N004["try"]
    N005["runner(...)"]
    N006["except (subprocess.SubprocessError, FileNotFoundError, OSError)"]
    N007["return False"]
    N008["return True"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
```

## issue_exists(...)

```mermaid
flowchart TD
    N001["issue_exists(...)"]
    N002["return verify_ref_exists(repo, number)"]
    N001 -->|"start"| N002
```

## get_issue_labels(...)

```mermaid
flowchart TD
    N001["get_issue_labels(...)"]
    N002["if runner is None"]
    N003["runner = subprocess.run"]
    N004["try"]
    N005["result = runner(...)"]
    N006["except (subprocess.SubprocessError, FileNotFoundError, OSError)"]
    N007["return None"]
    N008["raw = getattr(result, '<str>', b'') or b''"]
    N009["if isinstance(raw, bytes)"]
    N010["raw = decode(...)"]
    N011["return [line.strip() for line in raw.splitlines() if line.strip()]"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
```

## _format_no_closing_keyword_msg(...)

```mermaid
flowchart TD
    N001["_format_no_closing_keyword_msg(...)"]
    N002["return _shared_format_no_closing_keyword_msg(numbers, prefix='<str>')"]
    N001 -->|"start"| N002
```

## _verify(...)

```mermaid
flowchart TD
    N001["_verify(...)"]
    N002["if author is not None and author in _TRUSTED_BOT_LOGINS"]
    N003["print(...)"]
    N004["return 0"]
    N005["raw_body = replace(...)"]
    N006["cleaned = strip_html_comments(...)"]
    N007["refs = extract_refs(...)"]
    N008["if not refs"]
    N009["print(...)"]
    N010["return 1"]
    N011["fail = 0"]
    N012["for n in refs:     if issue_exists(repo, n):         print(f'<str>{n}<str>{repo}<str>')     else:         print(f'<str>{n}<str>{repo}<str>')         fail = 1"]
    N013["if fail"]
    N014["return 1"]
    N015["classified = classify_refs(...)"]
    N016["if any((kw in _CLOSING_KEYWORDS for kw, _ in classified))"]
    N017["return 0"]
    N018["if body_has_partial_marker(raw_body)"]
    N019["print(...)"]
    N020["return 0"]
    N021["refs_only = sorted(...)"]
    N022["for n in refs_only:     labels = get_issue_labels(repo, n)     if labels is None or _TRACKING_LABEL not in labels:         print(_format_no_closing_keyword_msg(refs_only))         return 1"]
    N023["print(...)"]
    N024["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 -->|"true"| N019
    N019 --> N020
    N018 -->|"false"| N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["if args.body_file is None"]
    N003["body = get(...)"]
    N004["body = read_text(...)"]
    N005["author = args.author if args.author is not None else os.environ.get('<str>')"]
    N006["return _verify(args.repo, body, author=author or None)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N003 --> N005
    N004 --> N005
    N005 --> N006
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
