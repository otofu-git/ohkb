# ohkb

**에이전트를 위한 간단한 로컬 지식 베이스.**

ohkb는 세션이 바뀌어도 지식을 저장하고, 찾고, 고치고, 정리할 수 있는 일관된 도구를 제공합니다. 지식 항목은 평범한 Markdown 파일이며, 검색에는 언제든 다시 만들 수 있는 로컬 SQLite FTS5 인덱스를 사용합니다.

ohkb는 언어 모델을 호출하지 않고, 임베딩을 생성하지 않으며, 벡터 데이터베이스를 요구하지 않습니다. 무엇을 남길지는 에이전트가 판단하고, ohkb는 그 지식을 정돈된 형태로 보관하고 검색할 수 있게 합니다.

[English](README.md) · [아키텍처](docs/ARCHITECTURE_kr.md) · [MCP 레퍼런스](docs/MCP_TOOLS_kr.md) · [로드맵](docs/ROADMAP_kr.md)

## 한눈에 보기

| | |
|---|---|
| **저장 형식** | YAML frontmatter가 포함된 Markdown 파일 |
| **검색** | BM25 랭킹을 사용하는 SQLite FTS5 |
| **인터페이스** | CLI와 로컬 MCP 서버 |
| **모델 사용** | 없음 |
| **네트워크 접근** | 핵심 명령에서는 없음 |
| **데이터 위치** | 기본값 `~/.ohkb`, `OHKB_DIR`로 변경 가능 |
| **Python** | 3.10 이상 |

## ohkb가 필요한 이유

에이전트가 지속적으로 활용해야 하는 지식은 대개 많지 않지만, 대화가 끝난 뒤에도 남아 있어야 합니다. 프로젝트 규칙, 중요한 결정, 조사 중 확인한 사실, 다음 세션에서도 기억해야 할 세부 정보가 여기에 해당합니다.

일반적인 메모 앱은 에이전트가 의존할 수 있는 예측 가능한 도구 규약을 제공하지 않습니다. 반대로 완전한 RAG 스택은 단순한 로컬 기억 장치만 필요한 상황에도 문서 수집 파이프라인, 청킹, 임베딩, 외부 서비스를 추가할 수 있습니다. ohkb는 그 사이에 있습니다.

- 무엇을 학습하고 어떻게 분류할지는 에이전트가 결정합니다.
- 각 항목은 ohkb 없이도 읽고 수정할 수 있습니다.
- 태그와 별칭은 명시적인 검색 신호로 사용됩니다.
- 검색 데이터베이스는 인덱스일 뿐, 원본이 아닙니다.
- CLI와 MCP에서 같은 작업을 수행할 수 있습니다.

ohkb의 역할은 의도적으로 작습니다. 에이전트를 대신해 지식을 판단하거나 작성하는 시스템이 아니라, 에이전트가 기억하기 위해 사용하는 도구입니다.

## 설치

[uv](https://docs.astral.sh/uv/)로 CLI를 설치합니다.

```bash
uv tool install ohkb
```

pip을 사용해도 됩니다.

```bash
pip install ohkb
```

MCP 서버는 선택 사항입니다.

```bash
uv tool install "ohkb[serve]"
# 또는
pip install "ohkb[serve]"
```

설치가 끝나면 버전을 확인합니다.

```bash
ohkb --version
```

## 빠른 시작

먼저 데이터 디렉터리를 초기화합니다.

```bash
ohkb init
```

지식 항목을 하나 저장합니다.

```bash
ohkb learn "Python 3.13은 --disable-gil 옵션으로 GIL 없이 빌드할 수 있다." \
  --title "Free-threaded Python" \
  --category python \
  --tags "GIL,CPython,free-threading,PEP-703" \
  --aliases "nogil,no-GIL Python,GIL removal"
```

저장한 항목을 검색하고 읽습니다.

```bash
ohkb search "GIL"
ohkb get "python/free-threaded-python.md"
```

전체 구조와 현재 상태도 확인할 수 있습니다.

```bash
ohkb tree
ohkb status
ohkb lint
```

대부분의 명령은 `--json`을 지원합니다. 에이전트나 스크립트에서 CLI를 호출할 때는 JSON 출력을 권장합니다.

```bash
ohkb search "GIL" --json
ohkb get "python/free-threaded-python.md" --json
ohkb status --json
```

## 권장 에이전트 워크플로

안정적으로 사용하려면 매 세션에서 다음 순서를 따르는 것이 좋습니다.

1. `ohkb index`로 현재 구조를 확인합니다.
2. 새 항목을 만들기 전에 검색합니다.
3. 검색 결과가 반환한 정확한 경로로 항목을 읽습니다.
4. 한 번에 하나의 명확한 사실만 추가하거나 수정합니다.
5. `ohkb status` 또는 `ohkb lint`로 파일과 인덱스 상태를 확인합니다.

```bash
ohkb index
ohkb search "deployment rollback" --json
ohkb get "operations/deployment-rollback.md" --json
ohkb learn "..." -t "..." -c operations --tags "..." --aliases "..." --json
```

`learn`보다 `search`를 먼저 실행하는 습관이 중요합니다. 같은 사실을 여러 파일에 중복해서 저장하지 않고 지식 베이스를 작고 명확하게 유지할 수 있습니다.

## 지식 항목

각 항목은 `wiki/<category>/<slug>.md`에 저장됩니다. 제목이 `Free-threaded Python`이고 카테고리가 `python`이라면 파일 경로는 다음과 같습니다.

```text
wiki/python/free-threaded-python.md
```

파일은 YAML frontmatter가 포함된 표준 Markdown 형식입니다.

```markdown
---
title: Free-threaded Python
category: python
tags:
- GIL
- CPython
- free-threading
- PEP-703
aliases:
- nogil
- no-GIL Python
entity_type: concept
source: manual
created: '2026-08-13T04:00:00+00:00'
updated: '2026-08-13T04:00:00+00:00'
---

Python 3.13은 --disable-gil 옵션으로 GIL 없이 빌드할 수 있다.
```

파일 하나에는 하나의 명확한 사실만 담는 것이 좋습니다. 항목 길이는 약 3,000자 이하를 권장하며, 지나치게 긴 항목은 `ohkb lint`가 알려줍니다.

### 카테고리

카테고리는 여러 단계로 구성할 수 있습니다.

```bash
ohkb learn "..." \
  --title "CPython garbage collection" \
  --category "python/internals" \
  --tags "CPython,GC,memory"
```

이 명령은 `python/internals/cpython-garbage-collection.md`를 만듭니다. 상위 카테고리로 검색하면 그 아래의 하위 카테고리도 함께 조회됩니다.

```bash
ohkb search "garbage collection" --category python
```

### 태그와 별칭

태그와 별칭은 단순한 부가 정보가 아니라 검색 모델의 일부입니다.

- **태그**는 공통 개념을 가진 항목을 연결하며 `ohkb related`에서 사용됩니다.
- **별칭**은 다른 이름, 약어, 사용자가 실제로 검색할 만한 표현을 담습니다.

항목마다 의미 있는 태그 3~7개와 실제로 쓰이는 별칭 몇 개면 충분합니다. 항목을 구분하는 데 도움이 되지 않는 지나치게 넓은 표현은 피하는 편이 좋습니다.

## 검색

검색에는 SQLite FTS5와 BM25를 사용합니다. 필드 가중치는 다음 순서입니다.

```text
title > tags > aliases > content
```

검색어에는 prefix matching을 적용합니다. 먼저 검색어를 엄격하게 조합하고, 결과가 없을 때만 제한된 범위에서 더 넓게 검색합니다. 결과에는 `0`부터 `1` 사이의 상대 점수가 포함됩니다. 이 점수는 전체 지식 베이스에 대한 절대값이 아니라, 같은 결과 목록 안에서의 관련도를 나타냅니다.

```bash
ohkb search "python gil"
ohkb search "gil" --category python --limit 5
ohkb search "free threading" --json
```

임베딩은 생성하지 않습니다. 검색 품질은 간결한 본문, 분명한 제목, 항목을 저장할 때 선택한 태그와 별칭에서 나옵니다.

## 읽기와 수정

`get`은 줄 번호와 함께 항목을 반환합니다. 에이전트는 이 번호를 사용해 필요한 부분만 정확하게 수정할 수 있습니다.

```bash
ohkb get "python/free-threaded-python.md"
```

한 번의 명령에서는 한 가지 수정 작업만 수행합니다.

```bash
# 본문 한 줄 교체
ohkb edit "python/free-threaded-python.md" --line <line-number> "새 내용"

# 여러 줄 교체
ohkb edit "python/free-threaded-python.md" --lines 20-22 "교체할 내용"

# 삽입 또는 삭제
ohkb edit "python/free-threaded-python.md" --after 20 "추가 내용"
ohkb edit "python/free-threaded-python.md" --delete 21
```

`edit`으로 frontmatter를 변경할 수는 없습니다. 메타데이터는 `meta`로 수정합니다.

```bash
ohkb meta "python/free-threaded-python.md" --add-tags "verified,python-3.13"
ohkb meta "python/free-threaded-python.md" --add-aliases "free-threaded CPython"
ohkb meta "python/free-threaded-python.md" --title "Free-threaded CPython"
ohkb meta "python/free-threaded-cpython.md" --category "python/runtime"
```

제목이나 카테고리를 바꾸면 파일도 새 경로로 이동하고 기존 경로는 제거됩니다. 이동할 위치에 파일이 이미 있다면 덮어쓰지 않고 오류를 반환합니다.

## 보관과 복원

`forget`은 되돌릴 수 있는 보관 작업입니다.

```bash
ohkb forget "python/free-threaded-python.md" --reason "새 항목으로 대체됨"
```

해당 경로에서 가장 최근에 보관한 버전을 복원합니다.

```bash
ohkb restore "python/free-threaded-python.md"
```

보관 목록을 확인하거나 특정 버전을 직접 복원할 수도 있습니다.

```bash
ohkb restore --list
ohkb restore "python/free-threaded-python.md" --list
ohkb restore --archive "python/free-threaded-python__20260813T120000000000Z.md"
```

같은 경로를 여러 번 보관해도 이전 파일을 덮어쓰지 않습니다. ohkb는 각 버전을 타임스탬프가 붙은 별도 파일로 유지합니다.

## 로컬 원본 파일 활용

선택 사항인 `sources/` 디렉터리에는 가공하지 않은 로컬 자료의 사본을 보관할 수 있습니다. 정리된 지식 항목과 원본 자료를 분리하기 위한 공간입니다.

```bash
ohkb source add ./research-notes.txt
ohkb source list
```

`extract`는 로컬 텍스트 또는 HTML 파일에서 텍스트를 반환합니다. 에이전트는 이 결과를 검토하고 분류한 뒤 필요한 사실만 저장할 수 있습니다.

```bash
ohkb extract ./research-notes.txt --json
```

일반적인 자료 정리 흐름은 다음과 같습니다.

```text
source add → extract → 검토 및 분류 → 중복 검색 → learn
```

텍스트 추출은 로컬에서 결정적으로 동작합니다. 내용을 요약하거나 모델을 호출하지 않으며 URL에도 접근하지 않습니다. PDF, DOCX, 이미지, ZIP 같은 바이너리 형식은 먼저 텍스트로 변환해야 합니다. 추출할 파일은 개별 10 MiB, `sources/`로 복사할 파일은 개별 100 MiB로 제한됩니다.

## 파일이 원본입니다

ohkb는 Markdown 파일을 먼저 쓴 다음 SQLite 인덱스를 갱신합니다. 데이터베이스는 언제든 `wiki/` 파일만으로 다시 만들 수 있습니다.

```bash
ohkb reindex
```

다른 편집기로 파일을 직접 수정하거나 버전 관리 시스템에서 복원했을 때 이 원칙이 중요합니다. `status`는 파일과 인덱스가 서로 일치하는지 보여줍니다.

```bash
ohkb status --json
```

`in_sync`가 `false`라면 `ohkb reindex`를 실행합니다. `lint`는 더 자세한 상태를 검사하며 다음 문제를 찾을 수 있습니다.

- 인덱스에 등록되지 않은 파일
- 실제 파일 없이 인덱스에만 남은 경로
- 잘못된 frontmatter
- 태그 또는 별칭 누락
- 카테고리와 파일 이름 불일치
- 지나치게 긴 항목

## MCP 서버

`serve` extra를 설치한 다음 MCP 클라이언트가 stdio로 ohkb를 실행하도록 설정합니다.

```json
{
  "mcpServers": {
    "ohkb": {
      "command": "ohkb",
      "args": ["serve", "--mode", "managed"]
    }
  }
}
```

MCP 클라이언트가 실행되는 환경에서 `ohkb` 명령을 찾을 수 있어야 합니다. 서버는 로컬 stdio만 지원하며 HTTP 전송 방식은 제공하지 않습니다.

### 접근 모드

| 모드 | 동작 |
|------|------|
| `readonly` | 읽기, 검색, 상태 확인, 텍스트 추출, 로컬 인덱스 재구축 |
| `managed` | 쓰기 도구를 추가하고 변경 전에 클라이언트에 확인 요청 |
| `autonomous` | 확인 요청 없이 쓰기 도구 제공 |

```bash
ohkb serve --mode readonly
ohkb serve --mode managed
ohkb serve --mode autonomous
```

MCP에서 사용할 수 있는 주요 기능은 다음과 같습니다.

- 리소스: `ohkb://index`
- 프롬프트: `research`, `learn_from_text`, `organize`
- 읽기 도구: `index`, `search`, `get`, `tree`, `status`, `lint`, `reindex`, `log`, `related`, `extract`, `source_list`
- 쓰기 도구: `learn`, `edit`, `meta`, `forget`, `restore`, `source_add`

매개변수와 반환값은 [docs/MCP_TOOLS_kr.md](docs/MCP_TOOLS_kr.md)에서 확인할 수 있습니다.

## 데이터 디렉터리

모든 상태는 기본적으로 `~/.ohkb` 아래에 저장됩니다.

```text
~/.ohkb/
├── _meta.db           # SQLite 메타데이터와 FTS5 인덱스
├── wiki/
│   ├── _index.md      # 자동 생성되는 요약
│   └── <category>/
│       └── <slug>.md  # 지식 항목
├── sources/           # 선택 사항인 로컬 원본 파일
├── archive/           # 버전별로 보관된 항목
├── log.md             # 추가 전용 활동 로그
└── AGENTS.ohkb.md     # 자동 생성되는 에이전트 워크플로 안내서
```

서로 다른 지식 베이스를 사용하거나 데이터 위치를 바꾸려면 `OHKB_DIR`을 지정합니다.

```bash
export OHKB_DIR="$PWD/.ohkb"
ohkb init
```

이 디렉터리는 다른 환경으로 옮길 수 있습니다. 필요에 따라 백업하거나, 일반 도구로 검색하거나, 자체 데이터 정책에 맞춰 버전 관리에 포함할 수 있습니다. Markdown 파일이 남아 있다면 `_meta.db`는 보존하지 않아도 됩니다.

## CLI 명령 요약

| 명령 | 용도 |
|------|------|
| `ohkb index` | 자동 생성된 지식 요약 표시 |
| `ohkb search QUERY` | 카테고리와 결과 수를 선택해 검색 |
| `ohkb get PATH` | 줄 번호와 함께 항목 읽기 |
| `ohkb tree [PATH]` | 지정한 깊이까지 카테고리 탐색 |
| `ohkb status` | 항목 수, 카테고리, 인덱스 동기화 상태 확인 |
| `ohkb lint` | 메타데이터 품질과 파일·인덱스 무결성 검사 |
| `ohkb related PATH` | 공통 태그가 있는 항목 검색 |
| `ohkb log` | 최근 활동 로그 표시 |
| `ohkb learn [CONTENT]` | 항목 생성. `--file`로 본문 입력 가능 |
| `ohkb edit PATH` | 본문 줄 교체, 삽입 또는 삭제 |
| `ohkb meta PATH` | 태그, 별칭, 제목, 카테고리, 엔티티 유형 수정 |
| `ohkb forget PATH` | 항목을 버전별 보관소로 이동 |
| `ohkb restore [PATH]` | 보관 목록 확인 또는 항목 복원 |
| `ohkb reindex` | Markdown 파일로 SQLite 인덱스 재구축 |
| `ohkb source add/list` | 선택 사항인 로컬 원본 파일 관리 |
| `ohkb extract TARGET` | 로컬 텍스트 또는 HTML 파일에서 텍스트 추출 |
| `ohkb init` | 표준 데이터 구조와 에이전트 안내서 생성 |
| `ohkb serve` | 선택 사항인 로컬 MCP 서버 시작 |

전체 옵션은 `ohkb COMMAND --help`에서 확인할 수 있습니다. 명령이 성공하면 종료 코드 `0`을 반환하고, 오류는 stderr에 기록합니다. `--json`을 지원하는 명령은 stdout을 기계가 읽을 수 있는 JSON으로 유지합니다.

## 지원 범위

ohkb는 의도적으로 기능 범위를 제한합니다. 핵심 프로젝트에는 다음 기능이 포함되지 않습니다.

- 모델 호출 또는 자율적인 지식 생성
- 임베딩 또는 벡터 검색
- URL 크롤링과 문서 수집 파이프라인
- 자동 병합, 분할 또는 노후화 판단
- 웹 또는 HTTP 런타임

이 경계 덕분에 저장 형식을 이해하기 쉽고 도구 규약도 예측 가능한 상태로 유지됩니다. 향후 계획은 [로드맵](docs/ROADMAP_kr.md)에서 확인할 수 있습니다.

## 개발

저장소를 복제하고 개발 환경을 설치합니다.

```bash
git clone https://github.com/otofu-git/ohkb.git
cd ohkb
uv sync --extra dev
```

전체 검사를 실행합니다.

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv build
```

테스트는 mock 대신 실제 임시 파일시스템과 SQLite 데이터베이스를 사용합니다. 저장소의 아키텍처, 불변 조건, 기여 시 지켜야 할 규칙은 [AGENTS_kr.md](AGENTS_kr.md)에서 확인할 수 있습니다.

## 버전

현재 릴리스: **0.1.0**

향후 기능과 호환성 계획은 [docs/ROADMAP_kr.md](docs/ROADMAP_kr.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)
