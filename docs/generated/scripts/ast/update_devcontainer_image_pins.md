# AST graph: scripts/update_devcontainer_image_pins.py

This file is generated from `scripts/update_devcontainer_image_pins.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## validate_sha(...)

```mermaid
flowchart TD
    N001["validate_sha(...)"]
    N002["if not SHA_RE.fullmatch(sha)"]
    N003["raise ValueError(f'<str>{sha}')"]
    N004["return sha"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## update_agent_config(...)

```mermaid
flowchart TD
    N001["update_agent_config(...)"]
    N002["path = repo_root / '<str>' / agent / '<str>'"]
    N003["data = loads(...)"]
    N004["expected_prefix = f'{IMAGE_PREFIX}<str>{agent}<str>'"]
    N005["current = get(...)"]
    N006["if not isinstance(current, str) or not current.startswith(expected_prefix)"]
    N007["raise ValueError(f'{path}<str>{expected_prefix}')"]
    N008["updated = f'{expected_prefix}{sha}'"]
    N009["if current == updated"]
    N010["return False"]
    N011["data['<str>'] = updated"]
    N012["write_text(...)"]
    N013["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 --> N013
```

## replace_once(...)

```mermaid
flowchart TD
    N001["replace_once(...)"]
    N002["(updated, count) = subn(...)"]
    N003["if count != 1"]
    N004["raise ValueError(f'<str>{label}<str>{count}')"]
    N005["return (updated, updated != text)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## update_runbook(...)

```mermaid
flowchart TD
    N001["update_runbook(...)"]
    N002["path = repo_root / '<str>' / '<str>' / '<str>'"]
    N003["text = read_text(...)"]
    N004["changed = False"]
    N005["(text, did_change) = replace_once(...)"]
    N006["changed = changed or did_change"]
    N007["for agent in AGENTS:     pattern = re.compile(DOC_IMAGE_RE_TEMPLATE.format(agent=agent))     text, did_change = replace_once(text, pattern, f'<str>{sha}', label=f'{agent}<str>')     changed = changed or did_change"]
    N008["if changed"]
    N009["write_text(...)"]
    N010["return changed"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
```

## update_pins(...)

```mermaid
flowchart TD
    N001["update_pins(...)"]
    N002["validated_sha = validate_sha(...)"]
    N003["changed = False"]
    N004["for agent in AGENTS:     changed = update_agent_config(repo_root, agent, validated_sha) or changed"]
    N005["changed = update_runbook(repo_root, validated_sha) or changed"]
    N006["overlay_changes = generate(...)"]
    N007["changed = bool(overlay_changes) or changed"]
    N008["return changed"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## parse_args(...)

```mermaid
flowchart TD
    N001["parse_args(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["return parser.parse_args(argv)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = parse_args(...)"]
    N003["changed = update_pins(...)"]
    N004["print(...)"]
    N005["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
