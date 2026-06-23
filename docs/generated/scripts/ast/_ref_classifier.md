# AST graph: scripts/_ref_classifier.py

This file is generated from `scripts/_ref_classifier.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## strip_html_comments(...)

```mermaid
flowchart TD
    N001["strip_html_comments(...)"]
    N002["return HTML_COMMENT_RE.sub('<str>', body)"]
    N001 -->|"start"| N002
```

## classify_refs(...)

```mermaid
flowchart TD
    N001["classify_refs(...)"]
    N002["out = []"]
    N003["seen = set(...)"]
    N004["for m in REF_LINE_KEYWORD_RE.finditer(body):     key = (m.group(1).lower(), int(m.group(2)))     if key not in seen:         seen.add(key)         out.append(key)"]
    N005["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## body_has_partial_marker(...)

```mermaid
flowchart TD
    N001["body_has_partial_marker(...)"]
    N002["return PARTIAL_MARKER_RE.search(raw_body) is not None or PARTIAL_MARKER_PLAINTEXT_RE.search(raw_body) is not None"]
    N001 -->|"start"| N002
```

## format_no_closing_keyword_msg(...)

```mermaid
flowchart TD
    N001["format_no_closing_keyword_msg(...)"]
    N002["joined = join(...)"]
    N003["return f'{prefix}<str>{joined}<str>{TRACKING_LABEL}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```
