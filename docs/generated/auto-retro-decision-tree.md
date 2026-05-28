# Auto-retro decision tree

This file is generated from `scripts/auto_retro.py::run` by `python3 scripts/auto_retro.py decision-tree-doc`. Do not edit it by hand; update `run()` and regenerate instead.

```mermaid
flowchart TD
    N001["run(...)"]
    N002["pr = parse_event(...)"]
    N003["if not pr.merged"]
    N004["msg = f'PR #{pr.number} is not merged'"]
    N005["print(...)"]
    N006["_append_summary(...)"]
    N007["return 0"]
    N008["(skip, reason) = should_skip(...)"]
    N009["if skip"]
    N010["print(...)"]
    N011["_append_summary(...)"]
    N012["return 0"]
    N013["existing_items = search_retro_issues(...)"]
    N014["existing = find_existing_retro(...)"]
    N015["if existing is not None"]
    N016["msg = f'existing retro issue #{existing} for PR #{pr.number}'"]
    N017["print(...)"]
    N018["_append_summary(...)"]
    N019["return 0"]
    N020["if pr.title.lstrip().lower().startswith('fix(')"]
    N021["body_without_comments = strip_html_comments(...)"]
    N022["candidate_refs = extract_refs(...)"]
    N023["if candidate_refs"]
    N024["try"]
    N025["titles = fetch_issue_titles(...)"]
    N026["except subprocess.CalledProcessError"]
    N027["print(...)"]
    N028["titles = {}"]
    N029["target = find_target_retro_from_refs(...)"]
    N030["if target is not None"]
    N031["try"]
    N032["(changed, detail) = append_repair_history_row(...)"]
    N033["except subprocess.CalledProcessError"]
    N034["print(...)"]
    N035["_append_summary(...)"]
    N036["return 0"]
    N037["action = 'appended' if changed else 'skip'"]
    N038["print(...)"]
    N039["_append_summary(...)"]
    N040["return 0"]
    N041["try"]
    N042["has_inline_comments = has_review_comments(...)"]
    N043["except subprocess.CalledProcessError"]
    N044["print(...)"]
    N045["has_inline_comments = True"]
    N046["commit_subjects = None"]
    N047["if pr.commits > 1"]
    N048["try"]
    N049["commit_subjects = fetch_pr_commits(...)"]
    N050["except subprocess.CalledProcessError"]
    N051["print(...)"]
    N052["commit_subjects = None"]
    N053["signals = compute_repair_signals(...)"]
    N054["signal_summary = render_repair_signals(...)"]
    N055["if not any(signals.values())"]
    N056["msg = f'no repair signal fired ({signal_summary})'"]
    N057["print(...)"]
    N058["_append_summary(...)"]
    N059["return 0"]
    N060["past_retros = fetch_past_retro_labels(...)"]
    N061["prior = compute_prior_from_labels(...)"]
    N062["(prior_skip, prior_reason) = should_skip_by_prior(...)"]
    N063["if prior_skip"]
    N064["print(...)"]
    N065["_append_summary(...)"]
    N066["return 0"]
    N067["tentative = is_tentative_by_prior(...)"]
    N068["if commit_subjects is None"]
    N069["commit_subjects = fetch_pr_commits(...)"]
    N070["check_runs_unknown = False"]
    N071["try"]
    N072["check_runs = fetch_check_runs(...)"]
    N073["except subprocess.CalledProcessError"]
    N074["print(...)"]
    N075["check_runs = []"]
    N076["check_runs_unknown = True"]
    N077["verification_pairs = extract_verification_pairs(...)"]
    N078["pr_type = (extract_type_scope(pr.title) or '').split('(', 1)[0]"]
    N079["repair_rows = _repair_history_rows(...)"]
    N080["if not has_inline_comments and (not check_runs_unknown) and (not repair_rows or _has_only_exempt_policy_artifact_rows(repair_rows))"]
    N081["if repair_rows"]
    N082["msg = f'only policy-artifact repair rows generated ({signal_summary})'"]
    N083["msg = f'no standalone repair workload ({signal_summary})'"]
    N084["print(...)"]
    N085["_append_summary(...)"]
    N086["return 0"]
    N087["title = build_retro_title(...)"]
    N088["body = build_retro_body(...)"]
    N089["labels = issue_labels(...)"]
    N090["created = create_issue(...)"]
    N091["new_number = get(...)"]
    N092["new_url = created.get('html_url') or ''"]
    N093["back_link_status = 'skipped'"]
    N094["terminal_label_status = 'skipped'"]
    N095["if isinstance(new_number, int)"]
    N096["try"]
    N097["back_link_status = post_back_link_comment(...)"]
    N098["except subprocess.CalledProcessError"]
    N099["print(...)"]
    N100["back_link_status = 'failed'"]
    N101["try"]
    N102["apply_terminal_label(...)"]
    N103["terminal_label_status = 'applied'"]
    N104["except subprocess.CalledProcessError"]
    N105["print(...)"]
    N106["terminal_label_status = 'failed'"]
    N107["msg = f'created retro issue #{new_number} ({new_url}); back-link={back_link_status}; terminal-label={terminal_label_status}'"]
    N108["print(...)"]
    N109["_append_summary(...)"]
    N110["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N003 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N011 --> N012
    N009 -->|"false"| N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N015 -->|"false"| N020
    N020 -->|"true"| N021
    N021 --> N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 -->|"try"| N025
    N024 -->|"raises"| N026
    N026 --> N027
    N027 --> N028
    N025 --> N029
    N028 --> N029
    N029 --> N030
    N030 -->|"true"| N031
    N031 -->|"try"| N032
    N031 -->|"raises"| N033
    N033 --> N034
    N034 --> N035
    N035 --> N036
    N032 --> N037
    N037 --> N038
    N038 --> N039
    N039 --> N040
    N030 -->|"false"| N041
    N023 -->|"false"| N041
    N020 -->|"false"| N041
    N041 -->|"try"| N042
    N041 -->|"raises"| N043
    N043 --> N044
    N044 --> N045
    N042 --> N046
    N045 --> N046
    N046 --> N047
    N047 -->|"true"| N048
    N048 -->|"try"| N049
    N048 -->|"raises"| N050
    N050 --> N051
    N051 --> N052
    N049 --> N053
    N052 --> N053
    N047 -->|"false"| N053
    N053 --> N054
    N054 --> N055
    N055 -->|"true"| N056
    N056 --> N057
    N057 --> N058
    N058 --> N059
    N055 -->|"false"| N060
    N060 --> N061
    N061 --> N062
    N062 --> N063
    N063 -->|"true"| N064
    N064 --> N065
    N065 --> N066
    N063 -->|"false"| N067
    N067 --> N068
    N068 -->|"true"| N069
    N069 --> N070
    N068 -->|"false"| N070
    N070 --> N071
    N071 -->|"try"| N072
    N071 -->|"raises"| N073
    N073 --> N074
    N074 --> N075
    N075 --> N076
    N072 --> N077
    N076 --> N077
    N077 --> N078
    N078 --> N079
    N079 --> N080
    N080 -->|"true"| N081
    N081 -->|"true"| N082
    N081 -->|"false"| N083
    N082 --> N084
    N083 --> N084
    N084 --> N085
    N085 --> N086
    N080 -->|"false"| N087
    N087 --> N088
    N088 --> N089
    N089 --> N090
    N090 --> N091
    N091 --> N092
    N092 --> N093
    N093 --> N094
    N094 --> N095
    N095 -->|"true"| N096
    N096 -->|"try"| N097
    N096 -->|"raises"| N098
    N098 --> N099
    N099 --> N100
    N097 --> N101
    N100 --> N101
    N101 -->|"try"| N102
    N102 --> N103
    N101 -->|"raises"| N104
    N104 --> N105
    N105 --> N106
    N103 --> N107
    N106 --> N107
    N095 -->|"false"| N107
    N107 --> N108
    N108 --> N109
    N109 --> N110
```
