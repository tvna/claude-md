# AST graph: scripts/preflight_pr_template_shape.py

This file is generated from `scripts/preflight_pr_template_shape.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _claude_web_harness(...)

```mermaid
flowchart TD
    N001["_claude_web_harness(...)"]
    N002["env = os.environ if environ is None else environ"]
    N003["return env.get(_REMOTE_ENV_VAR, '<str>').strip().lower() == '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["return verify_pr_verification_pairs(body) + verify_pr_checklist_subsections(body) + verify_pr_allowed_sections(body) + verify_pr_agent_attribution_footer(body, harness_appends_footer=harness_appends_footer)"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["canonical = canonical_github_tool(...)"]
    N003["if canonical not in _TARGET_TOOLS"]
    N004["return None"]
    N005["body = get(...)"]
    N006["if not isinstance(body, str)"]
    N007["return None"]
    N008["harness_appends_footer = canonical == _HARNESS_FOOTER_APPEND_TOOL and _claude_web_harness(environ)"]
    N009["errors = evaluate(...)"]
    N010["if not errors"]
    N011["return None"]
    N012["joined = join(...)"]
    N013["reason = f'<str>{tool_name}<str>{joined}<str>'"]
    N014["if canonical == 'mcp__github__update_pull_request' and _claude_web_harness(environ) and any(('agent-attribution footer' in e for e in errors))"]
    N015["reason += '<str>'"]
    N016["return build_deny(reason)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide)"]
    N001 -->|"start"| N002
    N002 --> N003
```
