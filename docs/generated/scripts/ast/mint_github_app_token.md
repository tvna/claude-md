# AST graph: scripts/mint_github_app_token.py

This file is generated from `scripts/mint_github_app_token.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _b64url(...)

```mermaid
flowchart TD
    N001["_b64url(...)"]
    N002["return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('<str>')"]
    N001 -->|"start"| N002
```

## _sign_rs256(...)

```mermaid
flowchart TD
    N001["_sign_rs256(...)"]
    N002["openssl = which(...)"]
    N003["if openssl is None"]
    N004["raise MintError('<str>')"]
    N005["(fd, key_path) = mkstemp(...)"]
    N006["try"]
    N007["write(...)"]
    N008["close(...)"]
    N009["completed = run(...)"]
    N010["with contextlib.suppress(OSError):     Path(key_path).unlink()"]
    N011["if completed.returncode != 0"]
    N012["raise MintError('<str>')"]
    N013["return completed.stdout"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"try"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## build_jwt(...)

```mermaid
flowchart TD
    N001["build_jwt(...)"]
    N002["issued_at = int(time.time()) if now is None else now"]
    N003["header = {'<str>': '<str>', '<str>': '<str>'}"]
    N004["payload = {'<str>': issued_at - _JWT_BACKDATE_SECONDS, '<str>': issued_at + _JWT_LIFETIME_SECONDS, '<str>': app_id}"]
    N005["segments = [_b64url(json.dumps(header, separators=('<str>', '<str>')).encode('<str>')), _b64url(json.dumps(payload, separators=('<str>', '<str>')).encode('<str>'))]"]
    N006["signing_input = encode(...)"]
    N007["signature = _sign_rs256(...)"]
    N008["append(...)"]
    N009["return '<str>'.join(segments)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## request_installation_token(...)

```mermaid
flowchart TD
    N001["request_installation_token(...)"]
    N002["if not api_url.startswith('https://')"]
    N003["raise MintError('<str>')"]
    N004["url = f'{api_url.rstrip('<str>')}<str>{installation_id}<str>'"]
    N005["request = Request(...)"]
    N006["try"]
    N007["with urllib.request.urlopen(request, timeout=30) as response:     body = response.read()"]
    N008["except urllib.error.HTTPError"]
    N009["raise MintError(f'<str>{exc.code}<str>')"]
    N010["except (urllib.error.URLError, TimeoutError, OSError)"]
    N011["raise MintError(f'<str>{exc.__class__.__name__}')"]
    N012["try"]
    N013["token = json.loads(body)['<str>']"]
    N014["except (ValueError, KeyError, TypeError)"]
    N015["raise MintError('<str>')"]
    N016["if not isinstance(token, str) or not token"]
    N017["raise MintError('<str>')"]
    N018["return token"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N006 -->|"raises"| N010
    N010 --> N011
    N007 --> N012
    N012 -->|"try"| N013
    N012 -->|"raises"| N014
    N014 --> N015
    N013 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## _require_env(...)

```mermaid
flowchart TD
    N001["_require_env(...)"]
    N002["value = get(...)"]
    N003["if not value.strip()"]
    N004["raise MintError(f'{name}<str>')"]
    N005["return value"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _require_private_key(...)

```mermaid
flowchart TD
    N001["_require_private_key(...)"]
    N002["literal = get(...)"]
    N003["if literal.strip()"]
    N004["return literal"]
    N005["path = get(...)"]
    N006["if path.strip()"]
    N007["try"]
    N008["pem = read_text(...)"]
    N009["except OSError"]
    N010["raise MintError(f'<str>{path}<str>{exc.__class__.__name__}')"]
    N011["if not pem.strip()"]
    N012["raise MintError(f'<str>{path}<str>')"]
    N013["return pem"]
    N014["raise MintError('<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N006 -->|"false"| N014
```

## mint_from_env(...)

```mermaid
flowchart TD
    N001["mint_from_env(...)"]
    N002["app_id = _require_env(...)"]
    N003["installation_id = _require_env(...)"]
    N004["private_key_pem = _require_private_key(...)"]
    N005["api_url = get(...)"]
    N006["jwt_token = build_jwt(...)"]
    N007["return request_installation_token(jwt_token, installation_id, api_url=api_url)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["try"]
    N003["token = mint_from_env(...)"]
    N004["except MintError"]
    N005["print(...)"]
    N006["return 1"]
    N007["write(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 --> N008
```
