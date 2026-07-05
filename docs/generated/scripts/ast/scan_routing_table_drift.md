# AST graph: scripts/scan_routing_table_drift.py

This file is generated from `scripts/scan_routing_table_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_table_lines(...)

```mermaid
flowchart TD
    N001["extract_table_lines(...)"]
    N002["lines = splitlines(...)"]
    N003["try"]
    N004["start = next(...)"]
    N005["except StopIteration"]
    N006["raise TableParseError(f'<str>{_SECTION_HEADING!r}<str>')"]
    N007["body = lines[start + 1:]"]
    N008["try"]
    N009["header_idx = next(...)"]
    N010["except StopIteration"]
    N011["raise TableParseError('<str>')"]
    N012["data_start = header_idx + 2"]
    N013["rows = []"]
    N014["for line in body[data_start:]:     if not _TABLE_ROW_RE.match(line):         break     rows.append(line)"]
    N015["if not rows"]
    N016["raise TableParseError('<str>')"]
    N017["return rows"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## split_row(...)

```mermaid
flowchart TD
    N001["split_row(...)"]
    N002["cells = [cell.strip() for cell in row.strip().strip('<str>').split('<str>')]"]
    N003["if len(cells) != 3"]
    N004["raise TableParseError(f'<str>{len(cells)}<str>{row!r}')"]
    N005["return (cells[0], cells[1], cells[2])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## parse_condition(...)

```mermaid
flowchart TD
    N001["parse_condition(...)"]
    N002["tokens = findall(...)"]
    N003["if tokens == [_WILDCARD_TYPE_MARKER]"]
    N004["return {'<str>': True}"]
    N005["if 'AND NOT' in cell"]
    N006["(before, _, after) = partition(...)"]
    N007["result = {}"]
    N008["before_tokens = findall(...)"]
    N009["after_tokens = findall(...)"]
    N010["if before_tokens"]
    N011["result['<str>'] = before_tokens"]
    N012["if after_tokens"]
    N013["result['<str>'] = after_tokens"]
    N014["return result"]
    N015["if not tokens"]
    N016["raise TableParseError(f'<str>{cell!r}')"]
    N017["if len(tokens) > 1"]
    N018["expected = join(...)"]
    N019["if cell.strip() != expected"]
    N020["raise TableParseError(f'<str>{len(tokens)}<str>{expected!r}<str>{cell!r}')"]
    N021["return {'<str>': tokens}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
    N005 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N018 --> N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N017 -->|"false"| N021
```

## parse_action(...)

```mermaid
flowchart TD
    N001["parse_action(...)"]
    N002["text = strip(...)"]
    N003["for prefix, shape in _ACTION_PREFIXES:     if text.startswith(prefix):         return dict(shape)"]
    N004["raise TableParseError(f'<str>{cell!r}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## parse_body_read(...)

```mermaid
flowchart TD
    N001["parse_body_read(...)"]
    N002["normalized = lower(...)"]
    N003["if normalized not in _BODY_READ_VALUES"]
    N004["raise TableParseError(f'<str>{cell!r}')"]
    N005["return _BODY_READ_VALUES[normalized]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## parse_runbook_rules(...)

```mermaid
flowchart TD
    N001["parse_runbook_rules(...)"]
    N002["rules = []"]
    N003["for row in extract_table_lines(runbook_text):     condition_cell, action_cell, body_read_cell = split_row(row)     rule: dict[str, object] = {}     rule.update(parse_condition(condition_cell))     rule.update(parse_action(action_cell))     rule['<str>'] = parse_body_read(body_read_cell)     rules.append(rule)"]
    N004["return rules"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## normalize_registry_rules(...)

```mermaid
flowchart TD
    N001["normalize_registry_rules(...)"]
    N002["return [dict(rule) for rule in rules]"]
    N001 -->|"start"| N002
```

## diff_rules(...)

```mermaid
flowchart TD
    N001["diff_rules(...)"]
    N002["if len(runbook_rules) != len(registry_rules)"]
    N003["return f'<str>{len(runbook_rules)}<str>{len(registry_rules)}'"]
    N004["for i, (table_rule, registry_rule) in enumerate(zip(runbook_rules, registry_rules, strict=True)):     if table_rule != registry_rule:         return f'<str>{i}<str>{table_rule!r}<str>{registry_rule!r}'"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["try"]
    N003["runbook_text = read_text(...)"]
    N004["runbook_rules = parse_runbook_rules(...)"]
    N005["except (OSError, TableParseError)"]
    N006["return [f'<str>{_RUNBOOK_PATH}<str>{_SCRIPT}<str>{exc}']"]
    N007["try"]
    N008["registry_rules = normalize_registry_rules(...)"]
    N009["except TypeError"]
    N010["return [f'<str>{_SCRIPT}<str>{exc}']"]
    N011["mismatch = diff_rules(...)"]
    N012["if mismatch is not None"]
    N013["return [f'<str>{_RUNBOOK_PATH}<str>{_SCRIPT}<str>{mismatch}']"]
    N014["return []"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N002 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["if argv is None"]
    N003["argv = sys.argv[1:]"]
    N004["command = argv[0] if argv else None"]
    N005["if command != 'verify'"]
    N006["print(...)"]
    N007["return 64"]
    N008["parser = ArgumentParser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["args = parse_args(...)"]
    N012["errors = verify(...)"]
    N013["if errors"]
    N014["for message in errors:     print(message, file=sys.stderr)"]
    N015["print(...)"]
    N016["return 1"]
    N017["print(...)"]
    N018["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 --> N016
    N013 -->|"false"| N017
    N017 --> N018
```
