# AST graph: scripts/_auto_retro_render.py

This file is generated from `scripts/_auto_retro_render.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## build_retro_title(...)

```mermaid
flowchart TD
    N001["build_retro_title(...)"]
    N002["return f'<str>{pr.number}<str>'"]
    N001 -->|"start"| N002
```

## is_canonical_handoff_retro_title(...)

```mermaid
flowchart TD
    N001["is_canonical_handoff_retro_title(...)"]
    N002["return bool(_CANONICAL_RETRO_TITLE_RE.fullmatch(title.strip()))"]
    N001 -->|"start"| N002
```

## _escape_table_cell(...)

```mermaid
flowchart TD
    N001["_escape_table_cell(...)"]
    N002["return text.replace('<str>', '<str>').replace('<str>', '<str>').replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _repair_history_rows(...)

```mermaid
flowchart TD
    N001["_repair_history_rows(...)"]
    N002["rows = []"]
    N003["rendered_failed = 0"]
    N004["total_failed = 0"]
    N005["for entry in check_runs or []:     conclusion = str(entry.get('<str>') or '<str>')     if conclusion not in _CHECK_RUN_FAIL_CONCLUSIONS:         continue     total_failed += 1     if rendered_failed >= _CHECK_RUN_DISPLAY_CAP:         continue     rendered_failed += 1     name = str(entry.get('<str>') or '<str>')     completed = str(entry.get('<str>') or '<str>')     html_url = str(entry.get('<str>') or '<str>').strip()     summary_raw = entry.get('<str>')     summary = str(summary_raw).strip() if summary_raw else '<str>'     parts = [f'<str>{conclusion}<str>{completed}']     if html_url:         parts.append(f'<str>{html_url}')     if summary:         parts.append(f'<str>{summary}')     detail = '<str>'.join(parts) or _REPAIR_CAUSE_FILL     rows.append(RepairHistoryRow(f'<str>{name}', detail, next_action=_REPAIR_NEXT_ACTION_FILL))"]
    N006["overflow = total_failed - _CHECK_RUN_DISPLAY_CAP"]
    N007["if overflow > 0"]
    N008["append(...)"]
    N009["canonical_fix_index = None"]
    N010["if pr_type == 'fix'"]
    N011["for i, subject in enumerate(commit_subjects):     stripped_i = subject.strip()     if any((stripped_i.startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES)):         continue     if stripped_i.startswith('<str>'):         canonical_fix_index = i     break"]
    N012["for i, subject in enumerate(commit_subjects):     stripped = subject.strip()     if i == canonical_fix_index:         rows.append(RepairHistoryRow('<str>', f'{_POLICY_ARTIFACT_MARKER}<str>{subject}<str>', policy_artifact=True, next_action='<str>'))         continue     if stripped.startswith('<str>') or stripped.startswith('<str>') or stripped.startswith('<str>'):         rows.append(RepairHistoryRow('<str>', f'{_POLICY_ARTIFACT_MARKER}<str>{subject}<str>', policy_artifact=True, next_action='<str>'))"]
    N013["for subject in commit_subjects:     stripped = subject.strip()     if any((stripped.startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES)):         rows.append(RepairHistoryRow('<str>', f'{_POLICY_ARTIFACT_MARKER}<str>{subject}<str>', policy_artifact=True, next_action='<str>'))"]
    N014["for subject in commit_subjects:     if _is_revert_subject(subject):         rows.append(RepairHistoryRow('<str>', f'{_POLICY_ARTIFACT_MARKER}<str>{subject}<str>', policy_artifact=True, next_action='<str>'))"]
    N015["if pr_commit_count > 1"]
    N016["append(...)"]
    N017["for pair in verification_pairs or []:     if pair.passed:         continue     rows.append(RepairHistoryRow(f'<str>{pair.command}', f'{_POLICY_ARTIFACT_MARKER}<str>{pair.result}<str>', policy_artifact=True, next_action='<str>'))"]
    N018["return rows"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N017
    N017 --> N018
```

## _has_only_exempt_policy_artifact_rows(...)

```mermaid
flowchart TD
    N001["_has_only_exempt_policy_artifact_rows(...)"]
    N002["return bool(rows) and all((row.policy_artifact and row.repair != '<str>' for row in rows))"]
    N001 -->|"start"| N002
```

## _build_repair_history_table(...)

```mermaid
flowchart TD
    N001["_build_repair_history_table(...)"]
    N002["rows = _repair_history_rows(...)"]
    N003["header = '<str>'"]
    N004["if not rows"]
    N005["return header + '<str>'"]
    N006["body_rows = join(...)"]
    N007["footnote = '<str>'"]
    N008["if any((row.policy_artifact for row in rows))"]
    N009["footnote = f'<str>{_POLICY_ARTIFACT_MARKER}<str>'"]
    N010["return header + body_rows + footnote"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
```

## build_retro_body(...)

```mermaid
flowchart TD
    N001["build_retro_body(...)"]
    N002["type_scope = extract_type_scope(...)"]
    N003["pr_type = type_scope.split('<str>', 1)[0] if type_scope else '<str>'"]
    N004["fallback_note = '<str>'"]
    N005["if not type_scope"]
    N006["fallback_note = '<str>'"]
    N007["layer_str = '<str>'.join(pr.layer_labels) if pr.layer_labels else '<str>'"]
    N008["commits_block = '<str>'.join((f'<str>{subj}' for subj in commit_subjects)) if commit_subjects else '<str>'"]
    N009["repair_table = _build_repair_history_table(...)"]
    N010["triage_date = pr.merged_at[:10] if pr.merged_at else '<str>'"]
    N011["positive_control = '<str>' in repair_table"]
    N012["proposed_work_tail = '<str>'"]
    N013["verification_block = '<str>'"]
    N014["acceptance_block = '<str>'"]
    N015["if positive_control"]
    N016["proposed_work_tail = '<str>'"]
    N017["verification_block = '<str>'"]
    N018["acceptance_block = '<str>'"]
    N019["return f'<str>{pr.number}<str>{pr.title}<str>{pr.number}<str>{pr.title}<str>{pr.html_url}<str>{pr.merged_at}<str>{pr.merged_by_login or '<str>'}<str>{pr.user_login or '<str>'}<str>{layer_str}<str>{render_signals_fired_line(signals or {})}<str>{commits_block}<str>{fallback_note}<str>{repair_table}<str>{proposed_work_tail}<str>{verification_block}<str>{acceptance_block}<str>{pr.number}<str>{triage_date}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N015 -->|"false"| N019
```

## verify_retro_repair_completeness(...)

```mermaid
flowchart TD
    N001["verify_retro_repair_completeness(...)"]
    N002["open_idx = find(...)"]
    N003["close_idx = find(...)"]
    N004["if open_idx == -1 or close_idx == -1 or close_idx < open_idx"]
    N005["return []"]
    N006["block = body[open_idx:close_idx]"]
    N007["errors = []"]
    N008["for line in block.splitlines():     stripped = line.strip()     if not (stripped.startswith('<str>') and stripped.endswith('<str>')):         continue     if '<str>' in stripped:         continue     if set(stripped) <= set('<str>'):         continue     if _POLICY_ARTIFACT_MARKER in stripped:         continue     if '<str>' in stripped:         continue     cells = [cell.strip().replace('<str>', '<str>') for cell in re.split('<str>', stripped[1:-1])]     repair_name = cells[1] if len(cells) > 1 else '<str>'     if len(cells) < 4:         errors.append(f'<str>{repair_name}<str>{len(cells)}<str>')         continue     cause = cells[2]     next_action = cells[3]     if not cause or '<str>' in cause:         errors.append(f'<str>{repair_name}<str>')     if not next_action or '<str>' in next_action:         errors.append(f'<str>{repair_name}<str>')"]
    N009["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## find_target_retro_from_refs(...)

```mermaid
flowchart TD
    N001["find_target_retro_from_refs(...)"]
    N002["if not pr.title.lstrip().lower().startswith('fix(')"]
    N003["return None"]
    N004["body_without_comments = strip_html_comments(...)"]
    N005["refs = extract_refs(...)"]
    N006["for number in refs:     title = referenced_titles.get(number)     if title is None:         continue     if is_retro_issue_title(title):         return number"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## render_appended_row(...)

```mermaid
flowchart TD
    N001["render_appended_row(...)"]
    N002["return (_escape_table_cell(f'<str>{pr.number}'), _escape_table_cell(f'<str>{pr.title}<str>{pr.merged_at}'), _escape_table_cell(_REPAIR_NEXT_ACTION_FILL))"]
    N001 -->|"start"| N002
```

## _next_table_index(...)

```mermaid
flowchart TD
    N001["_next_table_index(...)"]
    N002["pattern = compile(...)"]
    N003["indexes = [int(m.group(1)) for m in pattern.finditer(table_text)]"]
    N004["return max(indexes) + 1 if indexes else 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _insert_appended_row(...)

```mermaid
flowchart TD
    N001["_insert_appended_row(...)"]
    N002["open_idx = find(...)"]
    N003["close_idx = find(...)"]
    N004["if open_idx == -1 or close_idx == -1 or close_idx < open_idx"]
    N005["return (body, False)"]
    N006["block = body[open_idx:close_idx]"]
    N007["needle = compile(...)"]
    N008["if needle.search(block)"]
    N009["return (body, False)"]
    N010["next_idx = _next_table_index(...)"]
    N011["new_line = f'<str>{next_idx}<str>{row[0]}<str>{row[1]}<str>{row[2]}<str>'"]
    N012["new_body = body[:close_idx] + new_line + body[close_idx:]"]
    N013["return (new_body, True)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
```

## find_existing_retro(...)

```mermaid
flowchart TD
    N001["find_existing_retro(...)"]
    N002["needle = compile(...)"]
    N003["for item in search_items:     title = item.get('<str>') or '<str>'     if not (is_retro_issue_title(title) or is_per_pr_retro_title(title)):         continue     if needle.search(title):         return item.get('<str>')"]
    N004["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## is_retro_untouched(...)

```mermaid
flowchart TD
    N001["is_retro_untouched(...)"]
    N002["section = _slice_section(...)"]
    N003["if not section.strip()"]
    N004["return False"]
    N005["checkboxes = findall(...)"]
    N006["if not checkboxes"]
    N007["return False"]
    N008["if any((state.lower() == 'x' for state in checkboxes))"]
    N009["return False"]
    N010["for comment in comments or []:     user = comment.get('<str>') or {}     login = user.get('<str>') or '<str>'     if login and login not in _SENTINEL_IGNORED_COMMENT_LOGINS:         return False"]
    N011["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
```

## is_retro_age_exceeded(...)

```mermaid
flowchart TD
    N001["is_retro_age_exceeded(...)"]
    N002["try"]
    N003["created = fromisoformat(...)"]
    N004["now = fromisoformat(...)"]
    N005["except (ValueError, AttributeError)"]
    N006["return False"]
    N007["if created.tzinfo is None"]
    N008["created = replace(...)"]
    N009["if now.tzinfo is None"]
    N010["now = replace(...)"]
    N011["delta = now - created"]
    N012["return delta.days > days"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N002 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N011 --> N012
```

## issue_labels(...)

```mermaid
flowchart TD
    N001["issue_labels(...)"]
    N002["labels = ['<str>', '<str>']"]
    N003["for lbl in layer_labels:     if lbl and lbl not in labels:         labels.append(lbl)"]
    N004["if tentative and RETRO_TENTATIVE not in labels"]
    N005["append(...)"]
    N006["return labels"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
```
