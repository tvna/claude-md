# AST graph: scripts/owasp_asi_mapping.py

This file is generated from `scripts/owasp_asi_mapping.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_section(...)

```mermaid
flowchart TD
    N001["extract_section(...)"]
    N002["lines = splitlines(...)"]
    N003["start = None"]
    N004["for index, line in enumerate(lines):     if line.startswith('<str>') and SECTION_ANCHOR in line:         start = index         break"]
    N005["if start is None"]
    N006["return None"]
    N007["end = len(...)"]
    N008["for index in range(start + 1, len(lines)):     if lines[index].startswith('<str>'):         end = index         break"]
    N009["return '<str>'.join(lines[start:end])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## _split_row(...)

```mermaid
flowchart TD
    N001["_split_row(...)"]
    N002["cells = [cell.strip() for cell in line.strip().split('<str>')]"]
    N003["if cells and cells[0] == ''"]
    N004["cells = cells[1:]"]
    N005["if cells and cells[-1] == ''"]
    N006["cells = cells[:-1]"]
    N007["return cells"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## _strip_code(...)

```mermaid
flowchart TD
    N001["_strip_code(...)"]
    N002["return value.strip().strip('<str>').strip()"]
    N001 -->|"start"| N002
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["section = extract_section(...)"]
    N003["if section is None"]
    N004["return [f'<str>{SECTION_ANCHOR}<str>']"]
    N005["seen = {}"]
    N006["errors = []"]
    N007["for line in section.splitlines():     if not line.lstrip().startswith('<str>'):         continue     cells = _split_row(line)     if len(cells) < 4:         continue     asi_id = _strip_code(cells[0]).upper()     if asi_id not in EXPECTED_IDS:         continue     seen[asi_id] = seen.get(asi_id, 0) + 1     status = cells[2].strip().lower()     rationale = cells[3].strip()     if status not in VALID_STATUSES:         errors.append(f'{asi_id}<str>{cells[2].strip()!r}<str>{sorted(VALID_STATUSES)}')     if not rationale:         errors.append(f'{asi_id}<str>')"]
    N008["for asi_id in EXPECTED_IDS:     count = seen.get(asi_id, 0)     if count == 0:         errors.append(f'{asi_id}<str>')     elif count > 1:         errors.append(f'{asi_id}<str>{count}<str>')"]
    N009["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["print(...)"]
    N006["return 1"]
    N007["errors = evaluate(...)"]
    N008["for message in errors:     print(f'<str>{message}', file=sys.stderr)"]
    N009["if errors"]
    N010["print(...)"]
    N011["return 1"]
    N012["print(...)"]
    N013["return 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
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
    N008["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
