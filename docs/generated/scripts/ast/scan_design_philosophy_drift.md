# AST graph: scripts/scan_design_philosophy_drift.py

This file is generated from `scripts/scan_design_philosophy_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## normalize_label(...)

```mermaid
flowchart TD
    N001["normalize_label(...)"]
    N002["text = replace(...)"]
    N003["return _NORMALIZE_WS_RE.sub('<str>', text).strip()"]
    N001 -->|"start"| N002
    N002 --> N003
```

## parse_master_sections(...)

```mermaid
flowchart TD
    N001["parse_master_sections(...)"]
    N002["return {int(match.group(1)) for line in text.splitlines() if (match := MASTER_SECTION_RE.match(line)) is not None}"]
    N001 -->|"start"| N002
```

## extract_section_3(...)

```mermaid
flowchart TD
    N001["extract_section_3(...)"]
    N002["lines = splitlines(...)"]
    N003["start = None"]
    N004["end = None"]
    N005["for index, line in enumerate(lines):     if DOC_SECTION_3_HEADING_RE.match(line):         start = index         continue     if start is not None and DOC_NEXT_SECTION_RE.match(line):         end = index         break"]
    N006["if start is None"]
    N007["return ([], 0)"]
    N008["if end is None"]
    N009["end = len(...)"]
    N010["return (lines[start:end], start + 1)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
```

## parse_doc_matrix_rows(...)

```mermaid
flowchart TD
    N001["parse_doc_matrix_rows(...)"]
    N002["return {int(match.group(1)) for line in section_lines if (match := DOC_MATRIX_ROW_RE.match(line)) is not None}"]
    N001 -->|"start"| N002
```

## parse_master_subtitles(...)

```mermaid
flowchart TD
    N001["parse_master_subtitles(...)"]
    N002["result = {}"]
    N003["pending = None"]
    N004["for line in text.splitlines():     section_match = MASTER_SECTION_RE.match(line)     if section_match:         pending = int(section_match.group(1))         continue     if pending is None:         continue     subtitle_match = MASTER_SUBTITLE_RE.match(line)     if subtitle_match:         result[pending] = subtitle_match.group(1)         pending = None"]
    N005["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## parse_doc_row_labels(...)

```mermaid
flowchart TD
    N001["parse_doc_row_labels(...)"]
    N002["return {int(match.group(1)): match.group(2) for line in section_lines if (match := DOC_ROW_LABEL_RE.match(line)) is not None}"]
    N001 -->|"start"| N002
```

## parse_glossary_entries(...)

```mermaid
flowchart TD
    N001["parse_glossary_entries(...)"]
    N002["lines = splitlines(...)"]
    N003["start = None"]
    N004["end = None"]
    N005["for i, line in enumerate(lines):     if DOC_GLOSSARY_HEADING_RE.match(line):         start = i + 1         continue     if start is not None and DOC_HEADING_RE.match(line):         end = i         break"]
    N006["if start is None"]
    N007["return set()"]
    N008["if end is None"]
    N009["end = len(...)"]
    N010["return {match.group(1) for line in lines[start:end] if (match := DOC_GLOSSARY_ENTRY_RE.match(line)) is not None}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
```

## parse_doc_wording_counts(...)

```mermaid
flowchart TD
    N001["parse_doc_wording_counts(...)"]
    N002["hits = []"]
    N003["for lineno, line in enumerate(text.splitlines(), start=1):     for match in DOC_WORDING_RE.finditer(line):         token = match.group(1).lower()         count = WORD_TO_INT.get(token, _safe_int(token))         if count is None:             continue         hits.append((lineno, match.group(0), count))"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _safe_int(...)

```mermaid
flowchart TD
    N001["_safe_int(...)"]
    N002["try"]
    N003["return int(token)"]
    N004["except ValueError"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## _verify(...)

```mermaid
flowchart TD
    N001["_verify(...)"]
    N002["if not master_path.exists()"]
    N003["print(...)"]
    N004["return 1"]
    N005["if not doc_path.exists()"]
    N006["print(...)"]
    N007["return 1"]
    N008["master_text = read_text(...)"]
    N009["doc_text = read_text(...)"]
    N010["master_sections = parse_master_sections(...)"]
    N011["if not master_sections"]
    N012["print(...)"]
    N013["return 1"]
    N014["expected = set(...)"]
    N015["if master_sections != expected"]
    N016["missing = sorted(...)"]
    N017["print(...)"]
    N018["return 1"]
    N019["(section_lines, section_offset) = extract_section_3(...)"]
    N020["if not section_lines"]
    N021["print(...)"]
    N022["return 1"]
    N023["matrix_rows = parse_doc_matrix_rows(...)"]
    N024["failures = 0"]
    N025["missing_in_doc = sorted(...)"]
    N026["if missing_in_doc"]
    N027["labels = join(...)"]
    N028["print(...)"]
    N029["failures += 1"]
    N030["extra_in_doc = sorted(...)"]
    N031["if extra_in_doc"]
    N032["labels = join(...)"]
    N033["print(...)"]
    N034["failures += 1"]
    N035["expected_count = max(...)"]
    N036["for lineno, phrase, count in parse_doc_wording_counts(doc_text):     if count != expected_count:         print(f'<str>{doc_path}<str>{lineno}<str>{phrase}<str>{count}<str>{expected_count}<str>', file=sys.stderr)         failures += 1"]
    N037["master_subtitles = parse_master_subtitles(...)"]
    N038["doc_row_labels = parse_doc_row_labels(...)"]
    N039["for n in sorted(master_sections & matrix_rows):     sub_text = master_subtitles.get(n)     label_text = doc_row_labels.get(n)     if sub_text is None or label_text is None:         continue     if normalize_label(sub_text) != normalize_label(label_text):         print(f'<str>{doc_path}<str>{section_offset}<str>{n}<str>{label_text}<str>{n}<str>{sub_text}<str>', file=sys.stderr)         failures += 1"]
    N040["glossary_entries = parse_glossary_entries(...)"]
    N041["missing_glossary = sorted(...)"]
    N042["if missing_glossary"]
    N043["labels = join(...)"]
    N044["print(...)"]
    N045["failures += 1"]
    N046["if failures"]
    N047["print(...)"]
    N048["return 1"]
    N049["print(...)"]
    N050["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
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
    N015 -->|"true"| N016
    N016 --> N017
    N017 --> N018
    N015 -->|"false"| N019
    N019 --> N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N023
    N023 --> N024
    N024 --> N025
    N025 --> N026
    N026 -->|"true"| N027
    N027 --> N028
    N028 --> N029
    N029 --> N030
    N026 -->|"false"| N030
    N030 --> N031
    N031 -->|"true"| N032
    N032 --> N033
    N033 --> N034
    N034 --> N035
    N031 -->|"false"| N035
    N035 --> N036
    N036 --> N037
    N037 --> N038
    N038 --> N039
    N039 --> N040
    N040 --> N041
    N041 --> N042
    N042 -->|"true"| N043
    N043 --> N044
    N044 --> N045
    N045 --> N046
    N042 -->|"false"| N046
    N046 -->|"true"| N047
    N047 --> N048
    N046 -->|"false"| N049
    N049 --> N050
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["if not args.master or not args.doc"]
    N003["print(...)"]
    N004["return 2"]
    N005["return _verify(Path(args.master), Path(args.doc))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
```

## resolve_base(...)

```mermaid
flowchart TD
    N001["resolve_base(...)"]
    N002["explicit = get(...)"]
    N003["if explicit"]
    N004["return explicit"]
    N005["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## changed_files(...)

```mermaid
flowchart TD
    N001["changed_files(...)"]
    N002["result = _run(...)"]
    N003["return frozenset((line.strip() for line in result.stdout.splitlines() if line.strip()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## has_matrix_ack(...)

```mermaid
flowchart TD
    N001["has_matrix_ack(...)"]
    N002["return _MATRIX_ACK_RE.search(body) is not None"]
    N001 -->|"start"| N002
```

## evaluate_coupling(...)

```mermaid
flowchart TD
    N001["evaluate_coupling(...)"]
    N002["if MASTER_PATH not in changed"]
    N003["return (0, [])"]
    N004["if DOC_PATH in changed"]
    N005["return (0, [])"]
    N006["if has_matrix_ack(body)"]
    N007["return (0, [])"]
    N008["return (1, [f'<str>{MASTER_PATH}<str>{DOC_PATH}<str>'])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _resolve_coupling_body(...)

```mermaid
flowchart TD
    N001["_resolve_coupling_body(...)"]
    N002["if args.body_file is not None"]
    N003["return Path(args.body_file).read_text(encoding='<str>')"]
    N004["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _cmd_verify_coupling(...)

```mermaid
flowchart TD
    N001["_cmd_verify_coupling(...)"]
    N002["base = args.base_ref or resolve_base()"]
    N003["try"]
    N004["body = _resolve_coupling_body(...)"]
    N005["except FileNotFoundError"]
    N006["print(...)"]
    N007["return 1"]
    N008["try"]
    N009["changed = changed_files(...)"]
    N010["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError)"]
    N011["print(...)"]
    N012["return 1"]
    N013["(code, errors) = evaluate_coupling(...)"]
    N014["if code == 0"]
    N015["if MASTER_PATH in changed"]
    N016["print(...)"]
    N017["print(...)"]
    N018["return 0"]
    N019["for line in errors:     print(line)"]
    N020["return 1"]
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
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N016 --> N018
    N017 --> N018
    N014 -->|"false"| N019
    N019 --> N020
```

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=True)"]
    N001 -->|"start"| N002
```

## _cmd_report(...)

```mermaid
flowchart TD
    N001["_cmd_report(...)"]
    N002["if not args.master or not args.doc"]
    N003["print(...)"]
    N004["return 2"]
    N005["master_path = Path(...)"]
    N006["doc_path = Path(...)"]
    N007["if not master_path.exists() or not doc_path.exists()"]
    N008["print(...)"]
    N009["return 1"]
    N010["master_sections = parse_master_sections(...)"]
    N011["(section_lines, _) = extract_section_3(...)"]
    N012["matrix_rows = parse_doc_matrix_rows(...)"]
    N013["print(...)"]
    N014["print(...)"]
    N015["print(...)"]
    N016["print(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
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
    N008["p_report = add_parser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["set_defaults(...)"]
    N012["p_coupling = add_parser(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["set_defaults(...)"]
    N016["args = parse_args(...)"]
    N017["return int(args.func(args))"]
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
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
```
