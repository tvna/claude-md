# AST graph: scripts/title_policy.py

This file is generated from `scripts/title_policy.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _load_title_policy_config(...)

```mermaid
flowchart TD
    N001["_load_title_policy_config(...)"]
    N002["with path.open('<str>') as fp:     data = tomllib.load(fp)"]
    N003["policy = get(...)"]
    N004["if not isinstance(policy, dict)"]
    N005["raise ValueError(f'<str>{path}')"]
    N006["types = get(...)"]
    N007["if not isinstance(types, list) or not types or any((not isinstance(item, str) or not item for item in types))"]
    N008["raise ValueError(f'{path}<str>')"]
    N009["scope_pattern = get(...)"]
    N010["if not isinstance(scope_pattern, str) or not scope_pattern"]
    N011["raise ValueError(f'{path}<str>')"]
    N012["compile(...)"]
    N013["return (tuple(types), scope_pattern)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
```

## is_ascii_title(...)

```mermaid
flowchart TD
    N001["is_ascii_title(...)"]
    N002["return title.isascii()"]
    N001 -->|"start"| N002
```

## follows_naming_convention(...)

```mermaid
flowchart TD
    N001["follows_naming_convention(...)"]
    N002["if kind in {'issue', 'pull_request'}"]
    N003["return _CONVENTIONAL_TITLE_RE.fullmatch(title) is not None"]
    N004["raise ValueError(f'<str>{kind!r}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## parse_title_parts(...)

```mermaid
flowchart TD
    N001["parse_title_parts(...)"]
    N002["match = fullmatch(...)"]
    N003["if match is None"]
    N004["return None"]
    N005["return TitleParts(type=match.group('<str>'), scope=match.group('<str>') or '<str>', summary=match.group('<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## pr_title_has_issue_ref(...)

```mermaid
flowchart TD
    N001["pr_title_has_issue_ref(...)"]
    N002["return _PR_ISSUE_REF_RE.search(title) is not None"]
    N001 -->|"start"| N002
```

## pr_title_issue_refs(...)

```mermaid
flowchart TD
    N001["pr_title_issue_refs(...)"]
    N002["return _PR_ISSUE_REF_RE.findall(title)"]
    N001 -->|"start"| N002
```

## pr_title_strip_issue_refs(...)

```mermaid
flowchart TD
    N001["pr_title_strip_issue_refs(...)"]
    N002["stripped = sub(...)"]
    N003["return re.sub('<str>', '<str>', stripped).strip()"]
    N001 -->|"start"| N002
    N002 --> N003
```

## pr_title_ref_is_exempt(...)

```mermaid
flowchart TD
    N001["pr_title_ref_is_exempt(...)"]
    N002["parts = parse_title_parts(...)"]
    N003["return parts is not None and parts.type == '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## allowed_types_csv(...)

```mermaid
flowchart TD
    N001["allowed_types_csv(...)"]
    N002["return '<str>'.join(_CONVENTIONAL_TYPES)"]
    N001 -->|"start"| N002
```

## type_fit_findings(...)

```mermaid
flowchart TD
    N001["type_fit_findings(...)"]
    N002["if kind not in {'issue', 'pull_request'}"]
    N003["raise ValueError(f'<str>{kind!r}')"]
    N004["parts = parse_title_parts(...)"]
    N005["if parts is None"]
    N006["return []"]
    N007["title_text = _normalize_policy_text(...)"]
    N008["body_text = _normalize_policy_text(...)"]
    N009["findings = []"]
    N010["if _has_performance_signal(title_text, body_text)"]
    N011["extend(...)"]
    N012["return findings"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
```

## format_type_fit_finding(...)

```mermaid
flowchart TD
    N001["format_type_fit_finding(...)"]
    N002["expected = join(...)"]
    N003["return f'{finding.reason}<str>{expected}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## naming_convention_hint(...)

```mermaid
flowchart TD
    N001["naming_convention_hint(...)"]
    N002["if kind in {'issue', 'pull_request'}"]
    N003["return '<str>'"]
    N004["raise ValueError(f'<str>{kind!r}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## describe_non_ascii(...)

```mermaid
flowchart TD
    N001["describe_non_ascii(...)"]
    N002["findings = []"]
    N003["for index, char in enumerate(title):     if char.isascii():         continue     findings.append(f'<str>{index}<str>{ord(char):<str>}')     if len(findings) >= limit:         break"]
    N004["return findings"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## verify_title(...)

```mermaid
flowchart TD
    N001["verify_title(...)"]
    N002["fail = 0"]
    N003["if not is_ascii_title(title)"]
    N004["details = join(...)"]
    N005["if details"]
    N006["details = f'<str>{details}<str>'"]
    N007["print(...)"]
    N008["fail = 1"]
    N009["if not follows_naming_convention(title, kind=kind)"]
    N010["print(...)"]
    N011["fail = 1"]
    N012["policy_body = '<str>' if _is_trusted_bot_author(author) else body or _body_from_env()"]
    N013["for finding in type_fit_findings(title, kind=kind, body=policy_body):     print(f'<str>{kind}<str>{format_type_fit_finding(finding)}')     fail = 1"]
    N014["if kind == 'pull_request' and pr_title_has_issue_ref(title) and (not pr_title_ref_is_exempt(title))"]
    N015["print(...)"]
    N016["fail = 1"]
    N017["if fail"]
    N018["return 1"]
    N019["print(...)"]
    N020["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N003 -->|"false"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
    N011 --> N014
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N016 --> N017
    N014 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N019 --> N020
```

## _normalize_policy_text(...)

```mermaid
flowchart TD
    N001["_normalize_policy_text(...)"]
    N002["return re.sub('<str>', '<str>', text.lower())"]
    N001 -->|"start"| N002
```

## _strip_resource_consumption_section(...)

```mermaid
flowchart TD
    N001["_strip_resource_consumption_section(...)"]
    N002["return _RESOURCE_CONSUMPTION_SECTION_RE.sub('<str>', body)"]
    N001 -->|"start"| N002
```

## _words(...)

```mermaid
flowchart TD
    N001["_words(...)"]
    N002["return set(re.findall('<str>', text))"]
    N001 -->|"start"| N002
```

## _has_performance_signal(...)

```mermaid
flowchart TD
    N001["_has_performance_signal(...)"]
    N002["if _words(title_text) & _PERFORMANCE_TERMS"]
    N003["return True"]
    N004["if any((phrase in title_text for phrase in _PERFORMANCE_PHRASES))"]
    N005["return True"]
    N006["return any((phrase in body_text for phrase in _PERFORMANCE_PHRASES))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _performance_type_findings(...)

```mermaid
flowchart TD
    N001["_performance_type_findings(...)"]
    N002["words = _words(...)"]
    N003["if parts.type == 'perf'"]
    N004["return []"]
    N005["if parts.type in {'docs', 'test'}"]
    N006["return []"]
    N007["if parts.type == 'ci' and words & _CI_INFRA_TERMS"]
    N008["return []"]
    N009["if parts.type == 'build' and words & _BUILD_INFRA_TERMS"]
    N010["return []"]
    N011["if parts.type == 'fix' and words & _PERF_FIX_TERMS"]
    N012["return []"]
    N013["if parts.type == 'feat' and ('benchmark' in words or 'metrics' in words)"]
    N014["return []"]
    N015["return [TypeFitFinding(reason='<str>', expected_types=tuple(sorted(_PERF_ADJACENT_ALLOWED_TYPES)))]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## _body_from_env(...)

```mermaid
flowchart TD
    N001["_body_from_env(...)"]
    N002["return os.environ.get('<str>') or os.environ.get('<str>') or '<str>'"]
    N001 -->|"start"| N002
```

## _author_from_env(...)

```mermaid
flowchart TD
    N001["_author_from_env(...)"]
    N002["return os.environ.get('<str>') or '<str>'"]
    N001 -->|"start"| N002
```

## _is_trusted_bot_author(...)

```mermaid
flowchart TD
    N001["_is_trusted_bot_author(...)"]
    N002["return bool(author) and author in _TRUSTED_BOT_LOGINS"]
    N001 -->|"start"| N002
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["title = args.title"]
    N003["if title is None"]
    N004["title = get(...)"]
    N005["body = _read_body_arg(...)"]
    N006["author = args.author if args.author is not None else _author_from_env()"]
    N007["return verify_title(title, kind=args.kind, body=body or '<str>', author=author)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _read_body_arg(...)

```mermaid
flowchart TD
    N001["_read_body_arg(...)"]
    N002["if args.body_file"]
    N003["return Path(args.body_file).read_text()"]
    N004["if args.body is not None"]
    N005["return args.body"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
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
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["set_defaults(...)"]
    N011["args = parse_args(...)"]
    N012["return args.func(args)"]
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
```
