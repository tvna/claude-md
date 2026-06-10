# AST graph: scripts/dependabot_automerge.py

This file is generated from `scripts/dependabot_automerge.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## classify_update_type(...)

```mermaid
flowchart TD
    N001["classify_update_type(...)"]
    N002["match = search(...)"]
    N003["if match is None"]
    N004["return None"]
    N005["old = _parse_version(...)"]
    N006["new = _parse_version(...)"]
    N007["if new[0] != old[0]"]
    N008["return '<str>'"]
    N009["if new[1] != old[1]"]
    N010["return '<str>'"]
    N011["if new[2] != old[2]"]
    N012["return '<str>'"]
    N013["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## infer_ecosystem(...)

```mermaid
flowchart TD
    N001["infer_ecosystem(...)"]
    N002["if changed_files and all((fnmatch.fnmatch(path, '.github/workflows/*') for path in changed_files))"]
    N003["return '<str>'"]
    N004["allowed_uv = {'<str>', '<str>'}"]
    N005["if changed_files and all((path in allowed_uv for path in changed_files))"]
    N006["return '<str>'"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## audit(...)

```mermaid
flowchart TD
    N001["audit(...)"]
    N002["pr = get(...)"]
    N003["if not isinstance(pr, dict)"]
    N004["return AuditResult(False, False, None, None, ['<str>'])"]
    N005["enabled = bool(...)"]
    N006["reasons = []"]
    N007["author = _nested_str(...)"]
    N008["head_ref = _nested_str(...)"]
    N009["raw_title = get(...)"]
    N010["title = raw_title if isinstance(raw_title, str) else '<str>'"]
    N011["labels = _label_names(...)"]
    N012["draft = bool(...)"]
    N013["if author not in _TRUSTED_BOT_LOGINS"]
    N014["append(...)"]
    N015["if not head_ref.startswith('dependabot/')"]
    N016["append(...)"]
    N017["if draft"]
    N018["append(...)"]
    N019["blocked_labels = sorted(...)"]
    N020["if blocked_labels"]
    N021["append(...)"]
    N022["blocked_threat_labels = sorted(...)"]
    N023["if blocked_threat_labels"]
    N024["append(...)"]
    N025["update_type = classify_update_type(...)"]
    N026["if update_type is None"]
    N027["append(...)"]
    N028["ecosystem = infer_ecosystem(...)"]
    N029["if ecosystem is None"]
    N030["append(...)"]
    N031["if update_type is not None and ecosystem is not None"]
    N032["rule = _matching_rule(...)"]
    N033["if rule is None"]
    N034["append(...)"]
    N035["allowed_update_types = set(...)"]
    N036["if update_type not in allowed_update_types"]
    N037["append(...)"]
    N038["allowed_paths = _string_list(...)"]
    N039["unexpected = _unexpected_paths(...)"]
    N040["if unexpected"]
    N041["append(...)"]
    N042["return AuditResult(eligible=not reasons, enabled=enabled, update_type=update_type, ecosystem=ecosystem, reasons=reasons)"]
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
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N019
    N019 --> N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 --> N025
    N023 -->|"false"| N025
    N025 --> N026
    N026 -->|"true"| N027
    N027 --> N028
    N026 -->|"false"| N028
    N028 --> N029
    N029 -->|"true"| N030
    N030 --> N031
    N029 -->|"false"| N031
    N031 -->|"true"| N032
    N032 --> N033
    N033 -->|"true"| N034
    N033 -->|"false"| N035
    N035 --> N036
    N036 -->|"true"| N037
    N037 --> N038
    N036 -->|"false"| N038
    N038 --> N039
    N039 --> N040
    N040 -->|"true"| N041
    N034 --> N042
    N041 --> N042
    N040 -->|"false"| N042
    N031 -->|"false"| N042
```

## render_markdown(...)

```mermaid
flowchart TD
    N001["render_markdown(...)"]
    N002["lines = ['<str>', '<str>', f'<str>{str(result.enabled).lower()}<str>', f'<str>{str(result.eligible).lower()}<str>', f'<str>{str(result.should_enable).lower()}<str>', f\"<str>{result.ecosystem or '<str>'}<str>\", f\"<str>{result.update_type or '<str>'}<str>\", '<str>']"]
    N003["if result.reasons"]
    N004["append(...)"]
    N005["extend(...)"]
    N006["append(...)"]
    N007["append(...)"]
    N008["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N005 --> N007
    N006 --> N007
    N007 --> N008
```

## _cmd_audit(...)

```mermaid
flowchart TD
    N001["_cmd_audit(...)"]
    N002["try"]
    N003["event = loads(...)"]
    N004["policy = loads(...)"]
    N005["changed_files = _read_changed_files(...)"]
    N006["except (OSError, json.JSONDecodeError, ValueError)"]
    N007["print(...)"]
    N008["return 1"]
    N009["result = audit(...)"]
    N010["markdown = render_markdown(...)"]
    N011["print(...)"]
    N012["if args.summary_file"]
    N013["write_text(...)"]
    N014["if args.output"]
    N015["_write_outputs(...)"]
    N016["return 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N004 --> N005
    N002 -->|"raises"| N006
    N006 --> N007
    N007 --> N008
    N005 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
```

## _parse_version(...)

```mermaid
flowchart TD
    N001["_parse_version(...)"]
    N002["parts = [int(part) for part in version.split('<str>')]"]
    N003["extend(...)"]
    N004["return (parts[0], parts[1], parts[2])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _nested_str(...)

```mermaid
flowchart TD
    N001["_nested_str(...)"]
    N002["current = data"]
    N003["for key in keys:
    if not isinstance(current, dict):
        return '<str>'
    current = current.get(key)"]
    N004["return current if isinstance(current, str) else '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _label_names(...)

```mermaid
flowchart TD
    N001["_label_names(...)"]
    N002["labels = get(...)"]
    N003["if not isinstance(labels, list)"]
    N004["return set()"]
    N005["names = set(...)"]
    N006["for label in labels:
    if isinstance(label, dict) and isinstance(label.get('<str>'), str):
        names.add(label['<str>'])"]
    N007["return names"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _matching_rule(...)

```mermaid
flowchart TD
    N001["_matching_rule(...)"]
    N002["rules = get(...)"]
    N003["if not isinstance(rules, list)"]
    N004["return None"]
    N005["for rule in rules:
    if isinstance(rule, dict) and rule.get('<str>') == ecosystem:
        return rule"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## _string_list(...)

```mermaid
flowchart TD
    N001["_string_list(...)"]
    N002["if not isinstance(value, list)"]
    N003["return []"]
    N004["return [item for item in value if isinstance(item, str)]"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _unexpected_paths(...)

```mermaid
flowchart TD
    N001["_unexpected_paths(...)"]
    N002["unexpected = []"]
    N003["for path in changed_files:
    if not any((fnmatch.fnmatch(path, pattern) for pattern in allowed_paths)):
        unexpected.append(path)"]
    N004["return unexpected"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _read_changed_files(...)

```mermaid
flowchart TD
    N001["_read_changed_files(...)"]
    N002["files = [line.strip() for line in path.read_text(encoding='<str>').splitlines()]"]
    N003["files = [line for line in files if line]"]
    N004["if not files"]
    N005["raise ValueError('<str>')"]
    N006["return files"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _write_outputs(...)

```mermaid
flowchart TD
    N001["_write_outputs(...)"]
    N002["with path.open('<str>', encoding='<str>') as handle:
    handle.write(f'<str>{str(result.eligible).lower()}<str>')
    handle.write(f'<str>{str(result.enabled).lower()}<str>')
    handle.write(f'<str>{str(result.should_enable).lower()}<str>')"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _list_pr_files(...)

```mermaid
flowchart TD
    N001["_list_pr_files(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>{pr_number}<str>'"]
    N003["(code, body) = apply_call(...)"]
    N004["if not 200 <= code < 300"]
    N005["raise RuntimeError(f'<str>{code}')"]
    N006["try"]
    N007["items = loads(...)"]
    N008["except json.JSONDecodeError"]
    N009["raise RuntimeError(f'<str>{exc}')"]
    N010["if not isinstance(items, list)"]
    N011["raise RuntimeError('<str>')"]
    N012["return [str(item['<str>']) for item in items if isinstance(item, dict) and '<str>' in item]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
```

## _enable_auto_merge(...)

```mermaid
flowchart TD
    N001["_enable_auto_merge(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>{pr_number}'"]
    N003["(code, body) = apply_call(...)"]
    N004["if not 200 <= code < 300"]
    N005["raise RuntimeError(f'<str>{code}')"]
    N006["try"]
    N007["pr_data = loads(...)"]
    N008["except json.JSONDecodeError"]
    N009["raise RuntimeError(f'<str>{exc}')"]
    N010["node_id = pr_data.get('<str>') if isinstance(pr_data, dict) else None"]
    N011["if not isinstance(node_id, str) or not node_id"]
    N012["raise RuntimeError('<str>')"]
    N013["(gql_code, response) = graphql_call(...)"]
    N014["if not 200 <= gql_code < 300"]
    N015["raise RuntimeError(f'<str>{gql_code}')"]
    N016["if 'errors' in response"]
    N017["raise RuntimeError(f\"<str>{response['<str>']}\")"]
    N018["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## _disable_auto_merge(...)

```mermaid
flowchart TD
    N001["_disable_auto_merge(...)"]
    N002["url = f'{_API_ROOT}<str>{repo}<str>{pr_number}'"]
    N003["(code, body) = apply_call(...)"]
    N004["if not 200 <= code < 300"]
    N005["raise RuntimeError(f'<str>{code}')"]
    N006["try"]
    N007["pr_data = loads(...)"]
    N008["except json.JSONDecodeError"]
    N009["raise RuntimeError(f'<str>{exc}')"]
    N010["if not isinstance(pr_data, dict)"]
    N011["raise RuntimeError('<str>')"]
    N012["node_id = get(...)"]
    N013["if not isinstance(node_id, str) or not node_id"]
    N014["raise RuntimeError('<str>')"]
    N015["if pr_data.get('auto_merge') is None"]
    N016["return False"]
    N017["(gql_code, response) = graphql_call(...)"]
    N018["if not 200 <= gql_code < 300"]
    N019["raise RuntimeError(f'<str>{gql_code}')"]
    N020["if 'errors' in response"]
    N021["raise RuntimeError(f\"<str>{response['<str>']}\")"]
    N022["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 -->|"true"| N021
    N020 -->|"false"| N022
```

## _cmd_list_files(...)

```mermaid
flowchart TD
    N001["_cmd_list_files(...)"]
    N002["token = get(...)"]
    N003["repo = get(...)"]
    N004["if not token"]
    N005["print(...)"]
    N006["return 1"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["try"]
    N011["pr_number = int(...)"]
    N012["except (TypeError, ValueError)"]
    N013["print(...)"]
    N014["return 1"]
    N015["try"]
    N016["files = _list_pr_files(...)"]
    N017["except RuntimeError"]
    N018["print(...)"]
    N019["return 1"]
    N020["output = Path(...)"]
    N021["mkdir(...)"]
    N022["write_text(...)"]
    N023["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N018 --> N019
    N016 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
```

## _cmd_request_automerge(...)

```mermaid
flowchart TD
    N001["_cmd_request_automerge(...)"]
    N002["token = get(...)"]
    N003["repo = get(...)"]
    N004["if not token"]
    N005["print(...)"]
    N006["return 1"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["try"]
    N011["pr_number = int(...)"]
    N012["except (TypeError, ValueError)"]
    N013["print(...)"]
    N014["return 1"]
    N015["try"]
    N016["_enable_auto_merge(...)"]
    N017["except RuntimeError"]
    N018["print(...)"]
    N019["return 1"]
    N020["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N018 --> N019
    N016 --> N020
```

## _cmd_disable_automerge(...)

```mermaid
flowchart TD
    N001["_cmd_disable_automerge(...)"]
    N002["token = get(...)"]
    N003["repo = get(...)"]
    N004["if not token"]
    N005["print(...)"]
    N006["return 1"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["try"]
    N011["pr_number = int(...)"]
    N012["except (TypeError, ValueError)"]
    N013["print(...)"]
    N014["return 1"]
    N015["try"]
    N016["disabled = _disable_auto_merge(...)"]
    N017["except RuntimeError"]
    N018["print(...)"]
    N019["return 1"]
    N020["print(...)"]
    N021["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N018 --> N019
    N016 --> N020
    N020 --> N021
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_audit = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["set_defaults(...)"]
    N011["p_list_files = add_parser(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["set_defaults(...)"]
    N015["p_automerge = add_parser(...)"]
    N016["add_argument(...)"]
    N017["set_defaults(...)"]
    N018["p_disable = add_parser(...)"]
    N019["add_argument(...)"]
    N020["set_defaults(...)"]
    N021["args = parse_args(...)"]
    N022["return args.func(args)"]
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
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
```
