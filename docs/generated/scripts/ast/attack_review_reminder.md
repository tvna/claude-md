# AST graph: scripts/attack_review_reminder.py

This file is generated from `scripts/attack_review_reminder.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_template_block(...)

```mermaid
flowchart TD
    N001["extract_template_block(...)"]
    N002["lines = splitlines(...)"]
    N003["captured = []"]
    N004["capturing = False"]
    N005["closed = False"]
    N006["for line in lines:     if not capturing:         if begin_marker in line:             capturing = True             captured.append(line)         continue     captured.append(line)     if end_marker in line:         closed = True         break"]
    N007["if not capturing"]
    N008["raise ValueError(f'<str>{begin_marker!r}')"]
    N009["if not closed"]
    N010["raise ValueError(f'<str>{end_marker!r}')"]
    N011["return '<str>'.join(captured) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## count_h3(...)

```mermaid
flowchart TD
    N001["count_h3(...)"]
    N002["return sum((1 for line in template_text.splitlines() if line.startswith('<str>')))"]
    N001 -->|"start"| N002
```

## build_comment(...)

```mermaid
flowchart TD
    N001["build_comment(...)"]
    N002["header = join(...)"]
    N003["return f'{header}<str>{template_text}'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _append_summary(...)

```mermaid
flowchart TD
    N001["_append_summary(...)"]
    N002["block = join(...)"]
    N003["with Path(summary_file).open('<str>', encoding='<str>') as fh:     fh.write(block)"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_assemble(...)

```mermaid
flowchart TD
    N001["_cmd_assemble(...)"]
    N002["runbook_path = args.runbook"]
    N003["try"]
    N004["runbook_text = read_text(...)"]
    N005["except OSError"]
    N006["print(...)"]
    N007["return 1"]
    N008["try"]
    N009["template_text = extract_template_block(...)"]
    N010["except ValueError"]
    N011["print(...)"]
    N012["return 1"]
    N013["h3 = count_h3(...)"]
    N014["if h3 != args.expected_h3"]
    N015["print(...)"]
    N016["return 1"]
    N017["run_date = args.run_date or datetime.now(UTC).strftime('<str>')"]
    N018["comment = build_comment(...)"]
    N019["write_text(...)"]
    N020["if args.summary_file"]
    N021["_append_summary(...)"]
    N022["print(...)"]
    N023["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N022
    N022 --> N023
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["assemble_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["args = parse_args(...)"]
    N013["if args.cmd == 'assemble'"]
    N014["return _cmd_assemble(args)"]
    N015["return 0"]
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
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```
