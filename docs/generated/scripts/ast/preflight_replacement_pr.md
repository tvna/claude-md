# AST graph: scripts/preflight_replacement_pr.py

This file is generated from `scripts/preflight_replacement_pr.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_candidate(...)

```mermaid
flowchart TD
    N001["parse_candidate(...)"]
    N002["pull_request = get(...)"]
    N003["merged_at = get(...)"]
    N004["if isinstance(pull_request, dict)"]
    N005["merged_at = get(...)"]
    N006["number = get(...)"]
    N007["if not isinstance(number, int)"]
    N008["raise ValueError(f'<str>{number!r}')"]
    N009["state = get(...)"]
    N010["if not isinstance(state, str)"]
    N011["raise ValueError(f'<str>{number}<str>{state!r}')"]
    N012["created_at = get(...)"]
    N013["if not isinstance(created_at, str) or not created_at"]
    N014["raise ValueError(f'<str>{number}<str>{created_at!r}')"]
    N015["html_url = get(...)"]
    N016["title = get(...)"]
    N017["return CandidatePR(number=number, state=state.lower(), merged=bool(merged_at) or raw.get('<str>') is True, created_at=created_at, html_url=html_url if isinstance(html_url, str) else '<str>', title=title if isinstance(title, str) else '<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 --> N017
```

## parse_candidates(...)

```mermaid
flowchart TD
    N001["parse_candidates(...)"]
    N002["items = raw.get('<str>') if isinstance(raw, dict) else raw"]
    N003["if not isinstance(items, list)"]
    N004["raise ValueError('<str>')"]
    N005["return sorted((parse_candidate(item) for item in items), key=lambda pr: (pr.created_at, pr.number))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## has_complete_root_cause_note(...)

```mermaid
flowchart TD
    N001["has_complete_root_cause_note(...)"]
    N002["return all((heading in note for heading in ROOT_CAUSE_REQUIRED_HEADINGS))"]
    N001 -->|"start"| N002
```

## compute_metrics(...)

```mermaid
flowchart TD
    N001["compute_metrics(...)"]
    N002["replacement_count = max(...)"]
    N003["closed_superseded = sum(...)"]
    N004["merged_numbers = tuple(...)"]
    N005["first_created = candidates[0].created_at if candidates else None"]
    N006["elapsed = None"]
    N007["if first_created and now is not None"]
    N008["elapsed = max(...)"]
    N009["return GuardMetrics(candidate_count=len(candidates), replacement_count=replacement_count, closed_superseded_count=closed_superseded, merged_numbers=merged_numbers, first_pr_created_at=first_created, elapsed_seconds=elapsed)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
```

## decide_replacement(...)

```mermaid
flowchart TD
    N001["decide_replacement(...)"]
    N002["metrics = compute_metrics(...)"]
    N003["if metrics.merged_numbers"]
    N004["merged = join(...)"]
    N005["return GuardDecision(kind='<str>', metrics=metrics, reasons=(f'<str>{merged}', '<str>'))"]
    N006["if metrics.replacement_count >= 1 and (not has_complete_root_cause_note(root_cause_note))"]
    N007["missing = [heading for heading in ROOT_CAUSE_REQUIRED_HEADINGS if heading not in root_cause_note]"]
    N008["return GuardDecision(kind='<str>', metrics=metrics, reasons=('<str>', '<str>' + '<str>'.join(missing)))"]
    N009["return GuardDecision(kind='<str>', metrics=metrics, reasons=('<str>',))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
```

## format_close_marker(...)

```mermaid
flowchart TD
    N001["format_close_marker(...)"]
    N002["parts = [REPLACEMENT_CLOSE_MARKER, f'<str>{superseded_pr}', f'<str>{issue}']"]
    N003["if replacement_pr is not None"]
    N004["append(...)"]
    N005["return '<str>'.join(parts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## render_report(...)

```mermaid
flowchart TD
    N001["render_report(...)"]
    N002["metrics = decision.metrics"]
    N003["lines = [f'<str>{decision.kind}', f'<str>{metrics.candidate_count}', f'<str>{metrics.replacement_count}', f'<str>{metrics.closed_superseded_count}', '<str>' + ('<str>'.join((f'<str>{n}' for n in metrics.merged_numbers)) if metrics.merged_numbers else '<str>'), f'<str>{metrics.first_pr_created_at or '<str>'}', f'<str>{(metrics.elapsed_seconds if metrics.elapsed_seconds is not None else '<str>')}']"]
    N004["extend(...)"]
    N005["if decision.kind == 'allow'"]
    N006["insert(...)"]
    N007["insert(...)"]
    N008["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N006 --> N008
    N007 --> N008
```

## load_root_cause_note(...)

```mermaid
flowchart TD
    N001["load_root_cause_note(...)"]
    N002["parts = []"]
    N003["if path"]
    N004["append(...)"]
    N005["if inline"]
    N006["append(...)"]
    N007["return '<str>'.join(parts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## load_candidates_from_file(...)

```mermaid
flowchart TD
    N001["load_candidates_from_file(...)"]
    N002["return parse_candidates(json.loads(Path(path).read_text(encoding='<str>')))"]
    N001 -->|"start"| N002
```

## fetch_candidates(...)

```mermaid
flowchart TD
    N001["fetch_candidates(...)"]
    N002["query = quote(...)"]
    N003["(status, body) = apply_call(...)"]
    N004["if not 200 <= status < 300"]
    N005["raise RuntimeError(f'<str>{status}<str>{body[:200]}')"]
    N006["raw = loads(...)"]
    N007["items = raw.get('<str>') if isinstance(raw, dict) else None"]
    N008["if not isinstance(items, list)"]
    N009["raise ValueError('<str>')"]
    N010["details = [fetch_pr_detail(repo, parse_candidate(item).number, token=token) for item in items]"]
    N011["return parse_candidates(details)"]
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
```

## fetch_pr_detail(...)

```mermaid
flowchart TD
    N001["fetch_pr_detail(...)"]
    N002["(status, body) = apply_call(...)"]
    N003["if not 200 <= status < 300"]
    N004["raise RuntimeError(f'<str>{number}<str>{status}<str>{body[:200]}')"]
    N005["data = loads(...)"]
    N006["if not isinstance(data, dict)"]
    N007["raise ValueError(f'<str>{number}<str>')"]
    N008["return data"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## parse_iso8601(...)

```mermaid
flowchart TD
    N001["parse_iso8601(...)"]
    N002["return datetime.fromisoformat(value.replace('<str>', '<str>')).astimezone(UTC)"]
    N001 -->|"start"| N002
```

## parse_now(...)

```mermaid
flowchart TD
    N001["parse_now(...)"]
    N002["if value is None"]
    N003["return None"]
    N004["return parse_iso8601(value)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _build_parser(...)

```mermaid
flowchart TD
    N001["_build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["marker = add_parser(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["return parser"]
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
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = parse_args(...)"]
    N003["if args.command == 'close-marker'"]
    N004["print(...)"]
    N005["return 0"]
    N006["try"]
    N007["if args.candidates_json"]
    N008["candidates = load_candidates_from_file(...)"]
    N009["token = os.environ.get('<str>') or os.environ.get('<str>')"]
    N010["if not token"]
    N011["print(...)"]
    N012["return 1"]
    N013["candidates = fetch_candidates(...)"]
    N014["except (OSError, RuntimeError, ValueError, json.JSONDecodeError)"]
    N015["print(...)"]
    N016["return 1"]
    N017["try"]
    N018["root_cause_note = load_root_cause_note(...)"]
    N019["decision = decide_replacement(...)"]
    N020["except (OSError, ValueError)"]
    N021["print(...)"]
    N022["return 1"]
    N023["report = render_report(...)"]
    N024["stream = sys.stdout if decision.kind == '<str>' else sys.stderr"]
    N025["print(...)"]
    N026["return 0 if decision.kind == '<str>' else 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"try"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N013
    N006 -->|"raises"| N014
    N014 --> N015
    N015 --> N016
    N008 --> N017
    N013 --> N017
    N017 -->|"try"| N018
    N018 --> N019
    N017 -->|"raises"| N020
    N020 --> N021
    N021 --> N022
    N019 --> N023
    N023 --> N024
    N024 --> N025
    N025 --> N026
```
