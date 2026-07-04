# AST graph: scripts/scan_review_in_progress_marker.py

This file is generated from `scripts/scan_review_in_progress_marker.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## has_in_progress_marker(...)

```mermaid
flowchart TD
    N001["has_in_progress_marker(...)"]
    N002["lowered_logins = {login.lower() for login in marker_logins}"]
    N003["for reaction in reactions:     if not isinstance(reaction, dict):         continue     if reaction.get('<str>') != _EYES_CONTENT:         continue     user = reaction.get('<str>')     if not isinstance(user, dict):         continue     login = user.get('<str>')     if isinstance(login, str) and login.lower() in lowered_logins:         return login"]
    N004["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## fetch_reactions(...)

```mermaid
flowchart TD
    N001["fetch_reactions(...)"]
    N002["return [item for item in paginate(f'<str>{repo}<str>{pr_number}<str>', token=token) if isinstance(item, dict)]"]
    N001 -->|"start"| N002
```

## _warn_fail_open(...)

```mermaid
flowchart TD
    N001["_warn_fail_open(...)"]
    N002["print(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## run_verify(...)

```mermaid
flowchart TD
    N001["run_verify(...)"]
    N002["if not repo"]
    N003["return _warn_fail_open('<str>')"]
    N004["if not pr_number"]
    N005["return _warn_fail_open('<str>')"]
    N006["if not token"]
    N007["return _warn_fail_open('<str>')"]
    N008["try"]
    N009["reactions = fetch_reactions(...)"]
    N010["except GitHubApiError"]
    N011["return _warn_fail_open(f'<str>{exc}')"]
    N012["marker_login = has_in_progress_marker(...)"]
    N013["if marker_login is not None"]
    N014["print(...)"]
    N015["return 1"]
    N016["print(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 --> N017
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
    N012["add_argument(...)"]
    N013["args = parse_args(...)"]
    N014["return run_verify(repo=args.repo, pr_number=args.pr_number, token=args.token)"]
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
```
