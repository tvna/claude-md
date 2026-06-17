# AST graph: scripts/preflight_pr_body.py

This file is generated from `scripts/preflight_pr_body.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _claude_web_harness(...)

```mermaid
flowchart TD
    N001["_claude_web_harness(...)"]
    N002["env = os.environ if environ is None else environ"]
    N003["return env.get(_REMOTE_ENV_VAR, '<str>').strip().lower() == '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["errors = []"]
    N003["required = required_sections(...)"]
    N004["headings = extract_headings(...)"]
    N005["for name in missing_sections(required, headings):     errors.append(f'<str>{name}<str>')"]
    N006["extend(...)"]
    N007["extend(...)"]
    N008["extend(...)"]
    N009["if not has_ack_marker(body) and detect_non_ascii(body)"]
    N010["append(...)"]
    N011["extend(...)"]
    N012["extend(...)"]
    N013["if issue is not None"]
    N014["cleaned = strip_html_comments(...)"]
    N015["refs = classify_refs(...)"]
    N016["if not refs"]
    N017["append(...)"]
    N018["if not any((n == issue for _, n in refs))"]
    N019["found = join(...)"]
    N020["append(...)"]
    N021["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 -->|"true"| N019
    N019 --> N020
    N017 --> N021
    N020 --> N021
    N018 -->|"false"| N021
    N013 -->|"false"| N021
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
    N007["args = parse_args(...)"]
    N008["body = read_text(...)"]
    N009["errors = evaluate(...)"]
    N010["for msg in errors:     print(msg)"]
    N011["if not errors"]
    N012["print(...)"]
    N013["return 0"]
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
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
```
