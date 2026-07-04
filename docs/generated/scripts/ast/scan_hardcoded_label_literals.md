# AST graph: scripts/scan_hardcoded_label_literals.py

This file is generated from `scripts/scan_hardcoded_label_literals.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## policy_family_names(...)

```mermaid
flowchart TD
    N001["policy_family_names(...)"]
    N002["if not isinstance(label_policy, dict)"]
    N003["return frozenset()"]
    N004["return frozenset((fam['<str>'] for fam in label_policy.get('<str>', []) or [] if isinstance(fam, dict) and isinstance(fam.get('<str>'), str)))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## retired_family_names(...)

```mermaid
flowchart TD
    N001["retired_family_names(...)"]
    N002["if not isinstance(label_policy, dict)"]
    N003["return frozenset()"]
    N004["families = set(...)"]
    N005["for entry in label_policy.get('<str>', []) or []:     if isinstance(entry, dict) and isinstance(entry.get('<str>'), str):         name = entry['<str>']         if '<str>' in name:             families.add(name.split('<str>', 1)[0])"]
    N006["return frozenset(families)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## known_families(...)

```mermaid
flowchart TD
    N001["known_families(...)"]
    N002["return policy_family_names(label_policy) | retired_family_names(label_policy) | RUNTIME_ONLY_FAMILIES"]
    N001 -->|"start"| N002
```

## build_label_re(...)

```mermaid
flowchart TD
    N001["build_label_re(...)"]
    N002["alternation = join(...)"]
    N003["return re.compile(f'<str>{alternation}<str>{_NAME_SEGMENT}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## iter_label_literals(...)

```mermaid
flowchart TD
    N001["iter_label_literals(...)"]
    N002["tree = parse(...)"]
    N003["hits = []"]
    N004["for node in ast.walk(tree):     if isinstance(node, ast.Constant) and isinstance(node.value, str) and label_re.match(node.value):         hits.append((node.lineno, node.value))"]
    N005["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## allowed_occurrences(...)

```mermaid
flowchart TD
    N001["allowed_occurrences(...)"]
    N002["return LITERAL_ALLOWLIST.get((path, literal), (0, '<str>'))[0]"]
    N001 -->|"start"| N002
```

## scan_file(...)

```mermaid
flowchart TD
    N001["scan_file(...)"]
    N002["if path in SSOT_HOME_FILES"]
    N003["return []"]
    N004["try"]
    N005["hits = iter_label_literals(...)"]
    N006["except SyntaxError"]
    N007["return [f'<str>{path}<str>{_SCRIPT}<str>{path}<str>{exc.msg}<str>{exc.lineno}<str>']"]
    N008["seen = Counter(...)"]
    N009["errors = []"]
    N010["for lineno, literal in hits:     seen[literal] += 1     allowed = allowed_occurrences(path, literal)     if seen[literal] <= allowed:         continue     if allowed:         reason = f'<str>{seen[literal]}<str>{allowed}<str>'     else:         reason = '<str>'     errors.append(f'<str>{path}<str>{lineno}<str>{_SCRIPT}<str>{literal!r}<str>{reason}')"]
    N011["return errors"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## list_script_files(...)

```mermaid
flowchart TD
    N001["list_script_files(...)"]
    N002["try"]
    N003["completed = run(...)"]
    N004["if completed.returncode == 0"]
    N005["return sorted((line.strip() for line in completed.stdout.splitlines() if _SCRIPT_PATH_RE.match(line.strip())))"]
    N006["except (OSError, subprocess.SubprocessError)"]
    N007["pass"]
    N008["return sorted((f'{scripts_dir}<str>{p.name}' for p in (repo_root / scripts_dir).glob('<str>') if p.is_file()))"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N004 -->|"true"| N005
    N002 -->|"raises"| N006
    N006 --> N007
    N004 -->|"false"| N008
    N007 --> N008
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["if not policy_family_names(label_policy)"]
    N003["return [f'<str>{_LABEL_POLICY_PATH}<str>{_SCRIPT}<str>']"]
    N004["label_re = build_label_re(...)"]
    N005["errors = []"]
    N006["for path in list_script_files(repo_root, scripts_dir):     source = (repo_root / path).read_text(encoding='<str>')     errors.extend(scan_file(path, source, label_re))"]
    N007["return errors"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
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
    N011["add_argument(...)"]
    N012["args = parse_args(...)"]
    N013["label_policy_path = _REPO_ROOT / args.label_policy"]
    N014["if not label_policy_path.exists()"]
    N015["print(...)"]
    N016["return 1"]
    N017["try"]
    N018["label_policy = loads(...)"]
    N019["except (OSError, tomllib.TOMLDecodeError)"]
    N020["print(...)"]
    N021["return 1"]
    N022["errors = verify(...)"]
    N023["if errors"]
    N024["for message in errors:     print(message, file=sys.stderr)"]
    N025["print(...)"]
    N026["return 1"]
    N027["print(...)"]
    N028["return 0"]
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
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 -->|"try"| N018
    N017 -->|"raises"| N019
    N019 --> N020
    N020 --> N021
    N018 --> N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 --> N025
    N025 --> N026
    N023 -->|"false"| N027
    N027 --> N028
```
