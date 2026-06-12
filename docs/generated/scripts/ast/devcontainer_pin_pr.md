# AST graph: scripts/devcontainer_pin_pr.py

This file is generated from `scripts/devcontainer_pin_pr.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _parse_published_sha(...)

```mermaid
flowchart TD
    N001["_parse_published_sha(...)"]
    N002["match = match(...)"]
    N003["return match.group('<str>') if match else None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _regenerate_pins(...)

```mermaid
flowchart TD
    N001["_regenerate_pins(...)"]
    N002["return update_devcontainer_image_pins.main([published_sha])"]
    N001 -->|"start"| N002
```

## render_pr_body(...)

```mermaid
flowchart TD
    N001["render_pr_body(...)"]
    N002["return issue_anchors.substitute(template_text.replace('<str>', github_sha))"]
    N001 -->|"start"| N002
```

## _has_pin_changes(...)

```mermaid
flowchart TD
    N001["_has_pin_changes(...)"]
    N002["return run_git(['<str>', '<str>']).returncode != 0"]
    N001 -->|"start"| N002
```

## _branch_exists_on_remote(...)

```mermaid
flowchart TD
    N001["_branch_exists_on_remote(...)"]
    N002["return run_git(['<str>', '<str>', '<str>', '<str>', branch]).returncode == 0"]
    N001 -->|"start"| N002
```

## _create_pin_branch(...)

```mermaid
flowchart TD
    N001["_create_pin_branch(...)"]
    N002["base_sha = _get_ref_sha(...)"]
    N003["_create_branch_ref(...)"]
    N004["additions = [{'<str>': path, '<str>': base64.b64encode(Path(path).read_bytes()).decode('<str>')} for path in files]"]
    N005["_create_commit_on_branch(...)"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _cmd_open(...)

```mermaid
flowchart TD
    N001["_cmd_open(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["repo = get(...)"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["sha = args.github_sha"]
    N011["branch = f'{args.branch_prefix}{sha}'"]
    N012["if not _has_pin_changes()"]
    N013["print(...)"]
    N014["return 0"]
    N015["if _branch_exists_on_remote(branch)"]
    N016["try"]
    N017["prs = _list_open_prs(...)"]
    N018["except RuntimeError"]
    N019["print(...)"]
    N020["return 1"]
    N021["if prs"]
    N022["existing = int(...)"]
    N023["print(...)"]
    N024["return 0"]
    N025["print(...)"]
    N026["try"]
    N027["_create_pin_branch(...)"]
    N028["except RuntimeError"]
    N029["print(...)"]
    N030["return 1"]
    N031["try"]
    N032["template_text = read_text(...)"]
    N033["except OSError"]
    N034["print(...)"]
    N035["return 1"]
    N036["body = render_pr_body(...)"]
    N037["try"]
    N038["(action, pr_number) = _upsert_pr(...)"]
    N039["except RuntimeError"]
    N040["print(...)"]
    N041["return 1"]
    N042["print(...)"]
    N043["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
    N015 -->|"true"| N016
    N016 -->|"try"| N017
    N016 -->|"raises"| N018
    N018 --> N019
    N019 --> N020
    N017 --> N021
    N021 -->|"true"| N022
    N022 --> N023
    N023 --> N024
    N021 -->|"false"| N025
    N015 -->|"false"| N026
    N026 -->|"try"| N027
    N026 -->|"raises"| N028
    N028 --> N029
    N029 --> N030
    N025 --> N031
    N027 --> N031
    N031 -->|"try"| N032
    N031 -->|"raises"| N033
    N033 --> N034
    N034 --> N035
    N032 --> N036
    N036 --> N037
    N037 -->|"try"| N038
    N037 -->|"raises"| N039
    N039 --> N040
    N040 --> N041
    N038 --> N042
    N042 --> N043
```

## _cmd_refresh(...)

```mermaid
flowchart TD
    N001["_cmd_refresh(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["repo = get(...)"]
    N007["if not repo"]
    N008["print(...)"]
    N009["return 1"]
    N010["prefix = args.branch_prefix"]
    N011["try"]
    N012["open_prs = _list_open_prs_by_prefix(...)"]
    N013["except RuntimeError"]
    N014["print(...)"]
    N015["return 1"]
    N016["if not open_prs"]
    N017["print(...)"]
    N018["return 0"]
    N019["pr = max(...)"]
    N020["old_number = int(...)"]
    N021["head_ref = get(...)"]
    N022["published_sha = _parse_published_sha(...)"]
    N023["if published_sha is None"]
    N024["print(...)"]
    N025["return 1"]
    N026["try"]
    N027["behind = _compare_behind(...)"]
    N028["except RuntimeError"]
    N029["print(...)"]
    N030["return 1"]
    N031["if behind <= 0"]
    N032["print(...)"]
    N033["try"]
    N034["_merge_pr_if_clean(...)"]
    N035["except RuntimeError"]
    N036["print(...)"]
    N037["return 1"]
    N038["return 0"]
    N039["target_short = args.target_sha[:12]"]
    N040["new_branch = f'{prefix}{published_sha}{_REFRESH_SEPARATOR}{target_short}'"]
    N041["if new_branch == head_ref"]
    N042["print(...)"]
    N043["try"]
    N044["_merge_pr_if_clean(...)"]
    N045["except RuntimeError"]
    N046["print(...)"]
    N047["return 1"]
    N048["return 0"]
    N049["rc = _regenerate_pins(...)"]
    N050["if rc != 0"]
    N051["print(...)"]
    N052["return 1"]
    N053["if not _has_pin_changes()"]
    N054["print(...)"]
    N055["try"]
    N056["_comment_pr(...)"]
    N057["_close_pr(...)"]
    N058["_delete_branch(...)"]
    N059["except RuntimeError"]
    N060["print(...)"]
    N061["return 0"]
    N062["if not _branch_exists_on_remote(new_branch)"]
    N063["try"]
    N064["_create_pin_branch(...)"]
    N065["except RuntimeError"]
    N066["print(...)"]
    N067["return 1"]
    N068["try"]
    N069["template_text = read_text(...)"]
    N070["except OSError"]
    N071["print(...)"]
    N072["return 1"]
    N073["body = render_pr_body(...)"]
    N074["try"]
    N075["(action, new_number) = _upsert_pr(...)"]
    N076["except RuntimeError"]
    N077["print(...)"]
    N078["return 1"]
    N079["print(...)"]
    N080["if new_number != old_number"]
    N081["try"]
    N082["_comment_pr(...)"]
    N083["_close_pr(...)"]
    N084["_delete_branch(...)"]
    N085["except RuntimeError"]
    N086["print(...)"]
    N087["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 --> N025
    N023 -->|"false"| N026
    N026 -->|"try"| N027
    N026 -->|"raises"| N028
    N028 --> N029
    N029 --> N030
    N027 --> N031
    N031 -->|"true"| N032
    N032 --> N033
    N033 -->|"try"| N034
    N033 -->|"raises"| N035
    N035 --> N036
    N036 --> N037
    N034 --> N038
    N031 -->|"false"| N039
    N039 --> N040
    N040 --> N041
    N041 -->|"true"| N042
    N042 --> N043
    N043 -->|"try"| N044
    N043 -->|"raises"| N045
    N045 --> N046
    N046 --> N047
    N044 --> N048
    N041 -->|"false"| N049
    N049 --> N050
    N050 -->|"true"| N051
    N051 --> N052
    N050 -->|"false"| N053
    N053 -->|"true"| N054
    N054 --> N055
    N055 -->|"try"| N056
    N056 --> N057
    N057 --> N058
    N055 -->|"raises"| N059
    N059 --> N060
    N058 --> N061
    N060 --> N061
    N053 -->|"false"| N062
    N062 -->|"true"| N063
    N063 -->|"try"| N064
    N063 -->|"raises"| N065
    N065 --> N066
    N066 --> N067
    N064 --> N068
    N062 -->|"false"| N068
    N068 -->|"try"| N069
    N068 -->|"raises"| N070
    N070 --> N071
    N071 --> N072
    N069 --> N073
    N073 --> N074
    N074 -->|"try"| N075
    N074 -->|"raises"| N076
    N076 --> N077
    N077 --> N078
    N075 --> N079
    N079 --> N080
    N080 -->|"true"| N081
    N081 -->|"try"| N082
    N082 --> N083
    N083 --> N084
    N081 -->|"raises"| N085
    N085 --> N086
    N084 --> N087
    N086 --> N087
    N080 -->|"false"| N087
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["open_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["refresh_p = add_parser(...)"]
    N014["add_argument(...)"]
    N015["add_argument(...)"]
    N016["add_argument(...)"]
    N017["add_argument(...)"]
    N018["add_argument(...)"]
    N019["add_argument(...)"]
    N020["add_argument(...)"]
    N021["add_argument(...)"]
    N022["args = parse_args(...)"]
    N023["if args.cmd == 'open'"]
    N024["return _cmd_open(args)"]
    N025["if args.cmd == 'refresh'"]
    N026["return _cmd_refresh(args)"]
    N027["return 0"]
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
    N022 --> N023
    N023 -->|"true"| N024
    N023 -->|"false"| N025
    N025 -->|"true"| N026
    N025 -->|"false"| N027
```
