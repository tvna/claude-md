# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

[English](./README.md) | [日本語](./README.ja.md) | [简体中文](./README.zh.md) | 한국어

개인용으로 조정한 에이전트 지침의 마스터 저장소입니다. [`microsoft/apm`](https://github.com/microsoft/apm)으로 [`CLAUDE.md`](./CLAUDE.md), [`AGENTS.md`](./AGENTS.md), [`GEMINI.md`](./GEMINI.md)를 컴파일하여, 다른 프로젝트에서 참조해 사용합니다. `apm compile --target all`은 apm-cli가 지원하는 모든 도구(Claude, Codex, Gemini CLI, 그리고 Copilot이나 `AGENTS.md`를 읽는 여러 클라이언트)를 위한 컴파일 결과를 생성합니다. 실제로 어떤 파일이 생성되는지는 각 도구의 컴파일 형식에 따라 다릅니다([도구별 보충](#도구별-보충) 참조).

## 목적

- AI 코딩 에이전트에게 건네는 원칙을 한곳에 모아, 어느 프로젝트에서나 일관된 동작이 되도록 합니다.
- 여기에는 **어느 프로젝트에서나 성립하는, 개인 수준의 보편적인 가이드라인** 만 두고, 프로젝트 고유의 규칙은 두지 않습니다.
- APM을 신뢰할 수 있는 생성 하네스로 사용합니다. `.apm/instructions/`를 편집하고, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`를 컴파일합니다.
- 각 프로젝트의 로컬 에이전트 지침은 이 마스터를 참조하고, 차이(delta)만 추가합니다.

## 여섯 가지 원칙

| # | 원칙 | 레이어 | 요지 |
|---|------|--------|------|
| 1 | Define the Goal with Plan Mode First | 목표와 계획 구조 | 3단계 이상의 작업이나 설계 판단을 포함하는 작업은 plan mode부터 시작한다. |
| 2 | Bound Inputs and Unknowns Before Coding | 구현 전 인식 정리 | 외부 텍스트를 신뢰할 수 없는 데이터로 다루고, 사실, 가정, 모호함을 나눈 뒤 구현한다. |
| 3 | Use Git Ecosystem Effectively | 딜리버리 하네스 | hooks, CI/CD, 선언적 의존성 관리 하네스를 스케일 전에 갖춘다. |
| 4 | Simplicity, Bounded by Safety | 안전 경계 | 요구를 충족하는 최소한으로 한다. 단 안전성, 도구 범위, 비밀 정보 취급을 희생하지 않는다. |
| 5 | Accelerate Scale with Quality | 품질이 스케일을 가능하게 한다 | 품질이야말로 출력의 스케일을 가능하게 하며, 둘은 비례해 늘어난다. 변경 범위는 좁게 유지하고, 품질이 저하되면 멈추고 다시 계획한다. |
| 6 | Be a Force Multiplier | 인계와 전달 | "LGTM"으로 끝내지 말고, 트레이드오프를 명시해 다른 사람이 판단을 따라갈 수 있게 한다. |

컴파일 후의 전문은 [`CLAUDE.md`](./CLAUDE.md) 또는 [`AGENTS.md`](./AGENTS.md)를 참조하세요.

## 빌드

잠긴(locked) uv 환경을 동기화한 뒤, 로컬 지침을 컴파일합니다.

```bash
uv sync --locked
uv run --with "apm-cli==$(python3 scripts/flake_pin.py version --tool apm)" apm compile --target all
```

APM은 `.apm/instructions/*.instructions.md`를 읽고, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`를 써냅니다. `--target all`은 flake.nix에 고정된 apm-cli(`scripts/flake_pin.py version --tool apm`)가 지원하는 모든 도구(`copilot, claude, cursor, opencode, codex, gemini, windsurf`)를 위해 컴파일합니다. `apm.yml`의 `target:` 필드는 더 좁은 범위(`claude`, `codex`)로 유지합니다. 이 필드는 `apm install` 방식의 skill 배치 범위도 겸하고 있어서, 본 저장소가 실제로 사용하지 않는 도구로의 배치는 의도적으로 좁혀 두었기 때문입니다. uv 설정에서는 의존성 해석에 14일간의 `exclude-newer` 지연을 적용합니다.

의도적으로 `.apm/`의 소스 파일을 변경했을 때는, 체크섬 잠금 파일을 갱신합니다.

```bash
python3 scripts/verify_apm_checksums.py update
python3 scripts/verify_apm_checksums.py verify
```

## 다른 프로젝트에서 사용하기

컴파일된 `CLAUDE.md` / `AGENTS.md`는 **커밋된 실제 파일** 로 들여옵니다(submodule도 symlink도 아닙니다). submodule은 커밋 포인터로만 저장되므로 fresh한 `git clone`(Claude Code on the web 세션 등)에서는 비어 있게 되고, symlink한 `CLAUDE.md`는 깨진 링크가 되어 아무것도 조용히 로드되지 않습니다. 아래 방식은 클론의 일부가 되는 실제 파일로 지침을 배치합니다.

### 1. 동기화 워크플로를 추가한다

[`docs/runbooks/consumer-instruction-sync.md`](./docs/runbooks/consumer-instruction-sync.md)의 동기화 워크플로를 자신의 프로젝트에 복사합니다. 고정한 태그 릴리스에서 컴파일된 지침을 가져오고, 공개된 `SHA256SUMS`로 각 파일을 검증하며, 커밋된 실제 파일로 써넣는 PR을 엽니다. 그 PR은 code-owner 게이트를 통해 머지하고, 자동 머지는 하지 마세요.

### 2. 프로젝트 고유 규칙을 추가한다

프로젝트 고유의 차이가 있다면, 마스터를 vendored 경로로 동기화하고 자신의 `CLAUDE.md`에서 import한 뒤, 그 아래에 프로젝트 고유의 차이만 적습니다.

```markdown
@.agents/claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

동기화는 vendored 파일만 덮어쓰므로, 자신의 `CLAUDE.md`가 망가지는 일은 없습니다.

### 3. 업데이트를 들여온다

리뷰된 PR에서 동기화 워크플로의 고정 릴리스 태그를 올립니다. 스케줄 실행이 업데이트 PR을 열어주므로, code-owner 게이트를 통해 머지합니다.

### 도구별 보충

- **Codex, Cursor, OpenCode, Windsurf 등 `AGENTS.md`를 읽는 도구** 를 위해서도, 같은 동기화로 `AGENTS.md`가 `CLAUDE.md`와 나란히 커밋된 실제 파일로 배치됩니다. 이 도구들에는 전용 컴파일 결과물이 없으며, apm-cli의 타깃 레지스트리에서 `AGENTS.md` 자체가 이들의 포맷으로 취급됩니다. 별도의 절차는 필요 없습니다.

- **Gemini CLI**: `CLAUDE.md` / `AGENTS.md`와 함께 `GEMINI.md`를 동기화하세요. 이 파일은 한 줄짜리 import 스텁(`@./AGENTS.md`)이며, Gemini CLI가 이 import를 해석하므로 내용은 항상 `AGENTS.md`와 일치합니다.

- **GitHub Copilot**: `apm compile --target all`은 `.github/copilot-instructions.md`도 생성할 수 있지만, 이는 진짜 *전역*(범위가 지정되지 않은) instruction primitive가 존재할 때만 해당합니다. 본 마스터의 유일한 instruction 소스는 `applyTo: "**/*"`를 선언하고 있으며, apm-cli의 컴파일러는 이를 "전역"이 아니라 "범위 지정됨"으로 취급하므로, 현재는 이 파일이 생성되지 않습니다. `AGENTS.md`를 네이티브로 읽는 Copilot 클라이언트에는 영향이 없습니다.

- **Devin** 은 APM이 `.agents/skills/`로 전개한 skills를 사용할 수 있습니다. hooks의 parity가 필요한 경우에는, 저장소 지침과 함께 `.devin/hooks.v1.json`을 들여오세요. 자세한 내용은 [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md)를 참조하세요.

- **context7 MCP** 는 일차 정보 문서의 취득을 가속하기 위해 `apm.yml`(`dependencies.mcp`)에서 선언합니다. 본 마스터는 선언만 하며, 사용하는 쪽이 `apm install --mcp context7`로 각자의 클라이언트에 연결합니다. 자세한 내용은 [`docs/runbooks/context7-mcp.md`](./docs/runbooks/context7-mcp.md)를 참조하세요.

## 버전 관리

universal text(`.apm/instructions/master.instructions.md` 와 컴파일된 `CLAUDE.md` / `AGENTS.md`)는 시맨틱 버저닝으로 관리합니다. `apm.yml: version` 이 단일 신뢰 출처(single source of truth)입니다. 여기서 "호환성"은 프로그램적 API가 아니라 사용하는 쪽 입장에서의 동작상 하위 호환성을 가리킵니다.

- **MAJOR** - 하위 호환성을 깨는 변경. 기존 규칙의 삭제·반전·약화, 새로운 금지나 필수 의무의 추가, 안정 참조의 파괴(원칙 번호 재배치, 키로 참조되는 섹션 앵커 개명, 용어 의미 변경).
- **MINOR** - 하위 호환되는 추가·명확화(새 규칙, 원칙, 섹션, 예시)로, 기존에 준수하던 동작이 그대로 준수 상태로 남는 것.
- **PATCH** - 규범과 무관한 표층 변경(오타, 서식, 링크 수정, 번역, 규칙의 의미를 보존하는 표현 변경).

universal text를 건드리는 PR의 bump 절차:

1. 정확히 하나의 `semver:major` / `semver:minor` / `semver:patch` 라벨로 심각도를 선언한다.
2. 선언한 구분에 맞춰 `apm.yml: version` 을 bump한다. universal text와 `apm.yml: version` 이 함께 변경되지 않거나 bump가 라벨과 일치하지 않으면 CI의 drift gate가 PR을 fail시킨다.
3. 머지 시 `v{version}` 태그가 자동 생성되어 릴리스 발행 플로우로 전달된다. 사용하는 쪽은 그 태그를 고정해 참조한다([다른 프로젝트에서 사용하기](#다른-프로젝트에서-사용하기) 참조).

결정 기록 전문은 [`docs/prd/semantic-versioning-universal-text.md`](./docs/prd/semantic-versioning-universal-text.md) 를 참조하세요.

## 변경 정책

- 모든 편집은 PR을 통해 들여온다. 머지 후에는 retrospective를 실시한다(Principle 3).
- 여기에 두는 것은 **모든 프로젝트에 해당하는 규칙** 만으로 한다. 프로젝트 고유의 규칙은 각 프로젝트 자신의 `CLAUDE.md`에 둔다.
- 추가보다 삭제를 우선한다(Principle 4).
- 새로 추가되거나 변경된, `scripts/` 아래의 workflow에서 호출되는 Python 스크립트는 [workflow script quality standard](./docs/standards/workflow-script-quality.md)를 충족할 것.
- `.apm/instructions/**`, `CLAUDE.md`, `AGENTS.md`를 편집하는 PR은 [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md)를 통과할 것(결정적 게이트가 green이 된 후에 적용하는 보안 중심 리뷰).
- 레인별(`prd/`, `standards/`, `runbooks/`, `archive/`) 문서 지도 전체는 [`docs/INDEX.md`](./docs/INDEX.md)를 참조.
