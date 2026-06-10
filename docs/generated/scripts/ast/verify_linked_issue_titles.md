# AST graph: scripts/verify_linked_issue_titles.py

This file is generated from `scripts/verify_linked_issue_titles.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _extract_refs(...)

```mermaid
flowchart TD
    N001["_extract_refs(...)"]
    N002["found = {int(m.group(2)) for m in REF_LINE_KEYWORD_RE.finditer(body)}"]
    N003["return sorted(found)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## get_issue_title(...)

```mermaid
flowchart TD
    N001["get_issue_title(...)"]
    N002["if runner is None"]
    N003["runner = subprocess.run"]
    N004["try"]
    N005["result = runner(...)"]
    N006["except (subprocess.SubprocessError, FileNotFoundError, OSError)"]
    N007["return None"]
    N008["raw = getattr(result, '<str>', b'') or b''"]
    N009["if isinstance(raw, bytes)"]
    N010["raw = decode(...)"]
    N011["return raw.strip() or None"]
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

## _validate_issue_title(...)

```mermaid
flowchart TD
    N001["_validate_issue_title(...)"]
    N002["errors = []"]
    N003["suffix = f'<str>{number}<str>'"]
    N004["if not title_policy.is_ascii_title(title)"]
    N005["details = join(...)"]
    N006["detail_str = f'<str>{details}<str>' if details else '<str>'"]
    N007["append(...)"]
    N008["if not title_policy.follows_naming_convention(title, kind='issue')"]
    N009["hint = naming_convention_hint(...)"]
    N010["append(...)"]
    N011["for finding in title_policy.type_fit_findings(title, kind='<str>'):
    formatted = title_policy.format_type_fit_finding(finding)
    errors.append(f'<str>{number}<str>{formatted}{suffix}')"]
    N012["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N004 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N010 --> N012
    N011 --> N012
```

## verify_linked_issue_titles(...)

```mermaid
flowchart TD
    N001["verify_linked_issue_titles(...)"]
    N002["cleaned = strip_html_comments(...)"]
    N003["refs = _extract_refs(...)"]
    N004["if not refs"]
    N005["print(...)"]
    N006["return 0"]
    N007["fail = 0"]
    N008["for n in refs:
    issue_title = get_issue_title(repo, n, runner=runner)
    if issue_title is None:
        print(f'<str>{n}<str>{repo}<str>')
        fail = 1
        continue
    errors = _validate_issue_title(issue_title, n)
    if errors:
        for line in errors:
            print(line)
        fail = 1
    else:
        print(f'<str>{n}<str>')"]
    N009["return fail"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["if args.body_file is None"]
    N003["body = get(...)"]
    N004["body = read_text(...)"]
    N005["return verify_linked_issue_titles(args.repo, body)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N003 --> N005
    N004 --> N005
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
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["try"]
    N010["return args.func(args)"]
    N011["except ValueError"]
    N012["print(...)"]
    N013["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N012 --> N013
```
