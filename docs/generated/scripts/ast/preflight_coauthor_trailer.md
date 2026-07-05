# AST graph: scripts/preflight_coauthor_trailer.py

This file is generated from `scripts/preflight_coauthor_trailer.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _emails_in_segment(...)

```mermaid
flowchart TD
    N001["_emails_in_segment(...)"]
    N002["angle_match = search(...)"]
    N003["if angle_match"]
    N004["return [m.group('<str>') for m in _EMAIL_BARE_RE.finditer(angle_match.group('<str>'))]"]
    N005["bare_match = search(...)"]
    N006["return [bare_match.group('<str>')] if bare_match else []"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## _commit_author_and_body(...)

```mermaid
flowchart TD
    N001["_commit_author_and_body(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return None"]
    N006["if result.returncode != 0 or _FIELD_SEP not in result.stdout"]
    N007["return None"]
    N008["(email, _, body) = partition(...)"]
    N009["return (email.strip(), body)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## find_redundant_trailers(...)

```mermaid
flowchart TD
    N001["find_redundant_trailers(...)"]
    N002["violations = []"]
    N003["for sha in shas:     parsed = _commit_author_and_body(runner, sha)     if parsed is None:         continue     author_email, body = parsed     for line_match in _TRAILER_LINE_RE.finditer(body):         rest = line_match.group('<str>')         seen_emails: set[str] = set()         for segment in _SEGMENT_SPLIT_RE.split(rest):             for trailer_email in _emails_in_segment(segment):                 key = trailer_email.casefold()                 if key in seen_emails:                     continue                 seen_emails.add(key)                 if key == author_email.casefold():                     violations.append(Violation(sha=sha, author_email=author_email, trailer_email=trailer_email))"]
    N004["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## check_coauthor_trailers(...)

```mermaid
flowchart TD
    N001["check_coauthor_trailers(...)"]
    N002["shas = commits_in_range(...)"]
    N003["if shas is None"]
    N004["return CoauthorTrailerResult(status='<str>', detail=f'<str>{base_ref}<str>')"]
    N005["violations = find_redundant_trailers(...)"]
    N006["if violations"]
    N007["return CoauthorTrailerResult(status='<str>', detail=f'{len(violations)}<str>{len(shas)}<str>{base_ref}<str>', violations=tuple(violations))"]
    N008["return CoauthorTrailerResult(status='<str>', detail=f'<str>{len(shas)}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## check_pushed_refs(...)

```mermaid
flowchart TD
    N001["check_pushed_refs(...)"]
    N002["(commits, undeterminable) = commits_for_pushed_refs(...)"]
    N003["if not commits and undeterminable"]
    N004["return CoauthorTrailerResult(status='<str>', detail=f'<str>{len(refs)}<str>')"]
    N005["violations = find_redundant_trailers(...)"]
    N006["scope = f'{len(commits)}<str>{len(refs)}<str>'"]
    N007["if violations"]
    N008["return CoauthorTrailerResult(status='<str>', detail=f'{len(violations)}<str>{scope}<str>', violations=tuple(violations))"]
    N009["return CoauthorTrailerResult(status='<str>', detail=f'<str>{scope}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
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
    N007["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["if runner is None"]
    N003["runner = make_runner(...)"]
    N004["(refs, remote) = read_push_refs(...)"]
    N005["if refs"]
    N006["result = check_pushed_refs(...)"]
    N007["result = check_coauthor_trailers(...)"]
    N008["if result.status == 'pass'"]
    N009["print(...)"]
    N010["return 0"]
    N011["if result.status == 'skip'"]
    N012["print(...)"]
    N013["return 0"]
    N014["print(...)"]
    N015["print(...)"]
    N016["for violation in result.violations:     print(f'<str>{violation.sha}<str>{violation.trailer_email!r}<str>{violation.author_email!r}', file=sys.stderr)"]
    N017["print(...)"]
    N018["return 1"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N006 --> N008
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["if argv is None"]
    N003["argv = sys.argv[1:]"]
    N004["command = argv[0] if argv else None"]
    N005["if command not in ('verify', '-h', '--help')"]
    N006["print(...)"]
    N007["return 64"]
    N008["args = parse_args(...)"]
    N009["return cmd_verify(args)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
```
