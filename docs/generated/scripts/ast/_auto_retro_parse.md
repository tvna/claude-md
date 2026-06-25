# AST graph: scripts/_auto_retro_parse.py

This file is generated from `scripts/_auto_retro_parse.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_event(...)

```mermaid
flowchart TD
    N001["parse_event(...)"]
    N002["pr = event.get('<str>') or {}"]
    N003["number = get(...)"]
    N004["if number is None"]
    N005["raise ValueError('<str>')"]
    N006["merged_by = pr.get('<str>') or {}"]
    N007["user = pr.get('<str>') or {}"]
    N008["labels = pr.get('<str>') or []"]
    N009["layer_labels = tuple(...)"]
    N010["return MergedPR(number=int(number), title=str(pr.get('<str>') or '<str>'), merged=bool(pr.get('<str>')), merged_at=str(pr.get('<str>') or '<str>'), merged_by_login=merged_by.get('<str>'), user_login=user.get('<str>'), layer_labels=layer_labels, html_url=str(pr.get('<str>') or '<str>'), body=str(pr.get('<str>') or '<str>'), commits=int(pr.get('<str>') or 0))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## extract_type_scope(...)

```mermaid
flowchart TD
    N001["extract_type_scope(...)"]
    N002["match = match(...)"]
    N003["if match is None"]
    N004["return '<str>'"]
    N005["return match.group(1)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## is_retro_pr(...)

```mermaid
flowchart TD
    N001["is_retro_pr(...)"]
    N002["stripped = lower(...)"]
    N003["token = extract_type_scope(stripped) or '<str>'"]
    N004["return '<str>' in token"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## is_retro_issue_title(...)

```mermaid
flowchart TD
    N001["is_retro_issue_title(...)"]
    N002["stripped = lower(...)"]
    N003["return stripped.startswith('<str>') or stripped.startswith('<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## is_per_pr_retro_title(...)

```mermaid
flowchart TD
    N001["is_per_pr_retro_title(...)"]
    N002["token = extract_type_scope(...)"]
    N003["return token.endswith('<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## should_skip(...)

```mermaid
flowchart TD
    N001["should_skip(...)"]
    N002["if pr.merged_by_login is not None and pr.merged_by_login in trusted_bots"]
    N003["return (True, f'<str>{pr.merged_by_login}<str>')"]
    N004["if pr.user_login is not None and pr.user_login in trusted_bots"]
    N005["return (True, f'<str>{pr.user_login}<str>')"]
    N006["if is_retro_pr(pr.title)"]
    N007["return (True, '<str>')"]
    N008["return (False, '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _count_merge_from_main(...)

```mermaid
flowchart TD
    N001["_count_merge_from_main(...)"]
    N002["return sum((1 for subject in subjects if any((subject.strip().startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES))))"]
    N001 -->|"start"| N002
```

## _is_revert_subject(...)

```mermaid
flowchart TD
    N001["_is_revert_subject(...)"]
    N002["stripped = strip(...)"]
    N003["return any((stripped.startswith(prefix) for prefix in _REVERT_PREFIXES)) or bool(_REVERT_CONVENTIONAL_RE.match(stripped))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _count_revert(...)

```mermaid
flowchart TD
    N001["_count_revert(...)"]
    N002["return sum((1 for subject in subjects if _is_revert_subject(subject)))"]
    N001 -->|"start"| N002
```

## _slice_section(...)

```mermaid
flowchart TD
    N001["_slice_section(...)"]
    N002["cleaned = strip_html_comments(...)"]
    N003["lines = splitlines(...)"]
    N004["target = casefold(...)"]
    N005["h2_pattern = compile(...)"]
    N006["start = None"]
    N007["end = len(...)"]
    N008["for i, line in enumerate(lines):     match = h2_pattern.match(line)     if match is None:         continue     text = match.group(1).rstrip('<str>').strip()     if start is None:         if text.casefold() == target:             start = i + 1         continue     end = i     break"]
    N009["if start is None"]
    N010["return '<str>'"]
    N011["return '<str>'.join(lines[start:end])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## _result_is_passing(...)

```mermaid
flowchart TD
    N001["_result_is_passing(...)"]
    N002["raw_text = strip(...)"]
    N003["text = raw_text"]
    N004["if text.startswith('`') and text.endswith('`') and (len(text) >= 2)"]
    N005["text = strip(...)"]
    N006["stripped = strip(...)"]
    N007["if stripped != text"]
    N008["text = stripped"]
    N009["if text.startswith('`') and text.endswith('`') and (len(text) >= 2)"]
    N010["text = strip(...)"]
    N011["if _RESULT_FAILING_COUNT_RE.search(text)"]
    N012["return False"]
    N013["if _RESULT_PASSING_NUMERIC_RE.match(text)"]
    N014["return True"]
    N015["if _RESULT_PASSING_ALL_UNIT_RE.match(text)"]
    N016["return True"]
    N017["if _RESULT_PASSING_COUNT_RE.match(text)"]
    N018["return True"]
    N019["if _RESULT_PASSING_TRAILING_OK_RE.search(text)"]
    N020["return True"]
    N021["if _RESULT_PASSING_NON_ASCII_ZERO_RE.search(raw_text)"]
    N022["return True"]
    N023["if _RESULT_PASSING_NIX_QUOTED_RE.match(text)"]
    N024["return True"]
    N025["if _RESULT_PASSING_GREP_N_RE.match(text)"]
    N026["return True"]
    N027["if _RESULT_PASSING_SHASUM_RE.match(text)"]
    N028["return True"]
    N029["if _RESULT_PASSING_HEX_HASH_RE.match(text)"]
    N030["return True"]
    N031["if _RESULT_PASSING_PKG_VERSION_RE.match(text)"]
    N032["return True"]
    N033["if _RESULT_PASSING_NIX_TOOL_RE.match(text)"]
    N034["return True"]
    N035["if _RESULT_PASSING_EXIT_ZERO_RE.search(text)"]
    N036["return True"]
    N037["if _RESULT_ENV_SKIP_RE.search(text)"]
    N038["return True"]
    N039["lower = lower(...)"]
    N040["raw_lower = lower(...)"]
    N041["return any((lower.startswith(prefix) for prefix in _RESULT_PASSING_PREFIXES)) or any((phrase in raw_lower for phrase in _RESULT_PASSING_OBSERVATION_PHRASES))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N007 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N021 -->|"true"| N022
    N021 -->|"false"| N023
    N023 -->|"true"| N024
    N023 -->|"false"| N025
    N025 -->|"true"| N026
    N025 -->|"false"| N027
    N027 -->|"true"| N028
    N027 -->|"false"| N029
    N029 -->|"true"| N030
    N029 -->|"false"| N031
    N031 -->|"true"| N032
    N031 -->|"false"| N033
    N033 -->|"true"| N034
    N033 -->|"false"| N035
    N035 -->|"true"| N036
    N035 -->|"false"| N037
    N037 -->|"true"| N038
    N037 -->|"false"| N039
    N039 --> N040
    N040 --> N041
```

## extract_verification_pairs(...)

```mermaid
flowchart TD
    N001["extract_verification_pairs(...)"]
    N002["section = _slice_section(...)"]
    N003["if not section.strip()"]
    N004["return []"]
    N005["lines = splitlines(...)"]
    N006["pairs = []"]
    N007["i = 0"]
    N008["while i < len(lines):     cmd_match = _VERIFICATION_COMMAND_RE.fullmatch(lines[i])     if cmd_match is not None and i + 1 < len(lines):         res_match = _VERIFICATION_RESULT_RE.fullmatch(lines[i + 1])         if res_match is not None:             cmd_text = lines[i].split('<str>', 1)[1].strip()             res_text = lines[i + 1].split('<str>', 1)[1].strip()             pairs.append(VerificationPair(command=cmd_text, result=res_text, passed=_result_is_passing(res_text)))             i += 2             continue     i += 1"]
    N009["return pairs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## extract_post_merge_checklist(...)

```mermaid
flowchart TD
    N001["extract_post_merge_checklist(...)"]
    N002["section = _slice_section(...)"]
    N003["if not section.strip()"]
    N004["return []"]
    N005["lines = splitlines(...)"]
    N006["h3_pattern = compile(...)"]
    N007["item_pattern = compile(...)"]
    N008["start = None"]
    N009["end = len(...)"]
    N010["for i, line in enumerate(lines):     match = h3_pattern.match(line)     if match is None:         continue     text = match.group(1).rstrip('<str>').strip()     base = text.split('<str>', 1)[0].strip().casefold()     if start is None:         if base == '<str>':             start = i + 1         continue     end = i     break"]
    N011["if start is None"]
    N012["return []"]
    N013["items = []"]
    N014["for line in lines[start:end]:     m = item_pattern.match(line)     if m is None:         continue     checked = m.group(1).lower() == '<str>'     items.append((m.group(2).strip(), checked))"]
    N015["return items"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 --> N015
```

## compute_repair_signals(...)

```mermaid
flowchart TD
    N001["compute_repair_signals(...)"]
    N002["fix_typed = startswith(...)"]
    N003["if commit_subjects is None"]
    N004["multi_commit = pr.commits > 1"]
    N005["pure_commits = pr.commits - _count_merge_from_main(commit_subjects) - _count_revert(commit_subjects)"]
    N006["multi_commit = pure_commits > 1"]
    N007["return {'<str>': bool(has_inline_comments), '<str>': fix_typed, '<str>': multi_commit}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N004 --> N007
    N006 --> N007
```

## render_repair_signals(...)

```mermaid
flowchart TD
    N001["render_repair_signals(...)"]
    N002["return '<str>'.join((f'{name}<str>{str(fired).lower()}' for name, fired in signals.items()))"]
    N001 -->|"start"| N002
```

## render_signals_fired_line(...)

```mermaid
flowchart TD
    N001["render_signals_fired_line(...)"]
    N002["fired = [name for name in _SIGNAL_NAMES if signals.get(name, False)]"]
    N003["if not fired"]
    N004["return '<str>'"]
    N005["return '<str>' + '<str>'.join(fired)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## parse_signals_from_retro_body(...)

```mermaid
flowchart TD
    N001["parse_signals_from_retro_body(...)"]
    N002["cleaned = strip_html_comments(...)"]
    N003["match = search(...)"]
    N004["if match is None"]
    N005["return frozenset()"]
    N006["payload = strip(...)"]
    N007["if not payload or payload.lower() == '(none)'"]
    N008["return frozenset()"]
    N009["known = set(...)"]
    N010["names = {part.strip() for part in payload.split('<str>') if part.strip()}"]
    N011["return frozenset(names & known)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
```
