# orag

[![PyPI](https://img.shields.io/pypi/v/orag.svg)](https://pypi.org/project/orag/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/anomalyco/orag/blob/main/LICENSE)

> **LLM 에이전트가 스스로 기억하고, 스스로 정리하는 지식 베이스.**
> 임베딩 없음. 벡터 DB 없음. 파일과 SQLite만 있으면 됨.

LLM 에이전트는 대화가 끝나면 모든 것을 잊습니다. orag는 이 문제를 해결합니다.
에이전트가 학습한 사실을 스스로 저장하고, 필요할 때 꺼내 쓰고, 낡은 지식을 스스로 정리할 수 있도록 설계된 도구입니다.
무거운 인프라 없이, 에이전트 자신이 지식을 관리하는 두뇌가 됩니다.

```
orag search "python GIL"
# ╭──────────────────────────────────────────────╮
# │ python/free-threaded-python.md  (score: 4.2) │
# │ Tags: GIL, CPython, free-threading, PEP-703  │
# ╰──────────────────────────────────────────────╯
```

## orag를 왜 사용하나요?

기존 RAG 도구는 하나의 사실을 저장하기 위해 임베딩 모델, 벡터 데이터베이스, API 호출이 필요합니다.
이는 곧 외부 서비스 의존, 높은 운영 비용, 느린 속도, 복잡한 마이그레이션을 의미합니다.

orag는 그 짐을 LLM 자신에게 돌려줍니다:

- **임베딩 불필요** -- 임베딩 역할을 LLM에게 위임합니다. LLM이 저장 시점에 의미 있는 태그와 별칭을 직접 결정하므로, 별도의 임베딩 모델 없이도 의미 기반 검색이 작동합니다. **로컬 모델에 특히 적합합니다.**
- **벡터 DB 불필요** -- 지식은 순수 마크다운 파일로 존재합니다. `git`, `grep`, 텍스트 에디터로 직접 읽고 관리할 수 있습니다.
- **가볍고 빠름** -- 단일 SQLite 파일, 네트워크 왕복 없음, 즉시 시작. 외부 서비스에 의존하지 않아 언제 어디서나 동일하게 동작합니다.
- **마이그레이션 간편** -- 모든 지식이 평문 마크다운 파일입니다. 복사하면 끝입니다. 벤더 락인 없음.
- **컨텍스트 비용 절약** -- 검색 결과는 기본적으로 간결하게 출력됩니다. `--json` 모드로 필요한 데이터만 정확하게 가져와 불필요한 토큰 낭비를 막습니다.

orag는 무거운 검색 인프라에 토큰을 낭비하지 않고, LLM 에이전트가 스스로 기억하고 진화하는 지식 베이스를 갖도록 설계되었습니다.

## 설치

```bash
# uv 사용 (권장)
uv tool install orag

# pip 사용
pip install orag

# pipx 사용
pipx install orag
```

## 빠른 시작

```bash
# 사실 저장
orag learn "Python 3.13은 --disable-gil 플래그로 GIL을 비활성화할 수 있습니다" \
  -t "자유 스레드 Python" -c python \
  --tags "GIL,CPython,free-threading,PEP-703" \
  --aliases "nogil,no-GIL Python,GIL removal"

# 검색
orag search "GIL"

# 줄 번호와 함께 읽기
orag get "python/free-threaded-python.md"

# 특정 줄 편집
orag edit "python/free-threaded-python.md" --line 11 "Python 3.14에서 안정화됨."

# 메타데이터 업데이트
orag meta "python/free-threaded-python.md" --add-tags "3.14,stable"

# 구조 탐색
orag tree

# 구식 지식 보관
orag forget "python/free-threaded-python.md"
```

모든 명령은 구조화된 출력을 위해 `--json`을 지원하므로 orag가 에이전트 도구로 자연스럽게 맞습니다.

## 작동 원리

```
┌─────────────────────────────────────┐
│             orag CLI                │
├─────────────────────────────────────┤
│           뇌 (핵심)                  │
│                                     │
│  ┌───────────┐   ┌───────────────┐  │
│  │ Wiki (MD) │   │ SQLite (FTS5) │  │
│  │           │◄─►│               │  │
│  │ 한 가지   │   │ BM25 검색     │  │
│  │ 사실 =    │   │ + 메타데이터  │  │
│  │ 한 파일   │   │               │  │
│  └───────────┘   └───────────────┘  │
└─────────────────────────────────────┘
```

지식은 YAML 전문(frontmatter)이 있는 원자적 마크다운 파일로 저장됩니다.
SQLite FTS5 인덱스는 제목, 태그, 별칭, 콘텐츠에 대한 빠른 전체 텍스트 검색을 제공합니다.
**LLM 자체가 임베딩 역할을 대신합니다.** 저장 시점에 어떤 태그와 별칭을 붙일지 LLM이 직접 결정하기 때문에, 별도의 임베딩 모델이나 벡터 DB 없이도 의미 기반 검색이 작동합니다.

### 파일 형식

```markdown
---
title: 자유 스레드 Python
category: python
tags: [GIL, CPython, free-threading, PEP-703]
aliases: [nogil, no-GIL Python, GIL removal]
created: 2026-04-07T12:00:00Z
---

Python 3.13은 실험적인 자유 스레딩 모드를 도입하며,
이를 통해 --disable-gil 플래그로 GIL을 비활성화할 수 있습니다.
```

### 데이터 디렉토리

```
~/.orag/
  _meta.db              # SQLite: FTS5 인덱스 + 메타데이터
  wiki/
    python/
      free-threaded-python.md
      asyncio-changes.md
    _tables/             # DB 테이블의 자동 생성 문서
  archive/               # 보관된 파일
```

## CLI 참고서

### 검색 & 읽기

```bash
orag search "query" [--json] [-c category]    # 전체 텍스트 검색
orag get "category/file.md" [--json]           # 줄 번호와 함께 파일 읽기
orag tree [--json]                             # 구조 탐색
orag status [--json]                           # 통계
orag lint [--json]                             # 상태 확인
```

### 쓰기

```bash
orag learn "content" -t "title" -c "category" \
  --tags "k1,k2" --aliases "a1,a2" \
  [--entity-type concept|person|event|product] \
  [--source manual|document|url] \
  [--overwrite]

# 파일에서
orag learn "" -t "title" -c "category" --tags "..." -f ./draft.md

# 표준 입력에서
echo "content" | orag learn -t "title" -c "category" --tags "..."
```

### 편집

```bash
orag edit "path" --line 10 "new content"       # 줄 바꾸기
orag edit "path" --lines 10-12 "replacement"   # 범위 바꾸기
orag edit "path" --after 5 "inserted line"     # 뒤에 삽입
orag edit "path" --delete 10                   # 줄 삭제
```

### 메타데이터

```bash
orag meta "path" --add-tags "new-tag"
orag meta "path" --remove-tags "old-tag"
orag meta "path" --add-aliases "synonym"
orag meta "path" --title "새로운 제목"
orag meta "path" --category "new-category"
```

### 보관

```bash
orag forget "path" [--reason "obsolete"]
```

## 설계 원칙

1. **한 가지 사실 = 한 파일.** 파일을 원자적으로 유지하고 작게 (< 3,000자). `orag lint`는 크기가 너무 큰 파일에 플래그를 표시합니다.
2. **태그와 별칭이 전부다.** 이것이 임베딩 없이 검색이 작동하는 방식입니다. LLM이 임베딩 모델을 대신해 저장 시점에 의미론적 이해를 제공합니다.
3. **배우기 전에 검색하세요.** 중복을 피하기 위해 항상 `orag learn` 전에 `orag search`를 하세요.
4. **컨텍스트는 비싸다.** 모든 출력은 기본적으로 간결합니다. `--json` 모드는 불필요한 토큰 낭비 없이 구조화된 데이터를 반환합니다.
5. **파일이 진실이다.** 순수 마크다운은 지식 베이스를 `git commit`, `grep`, `cat`할 수 있다는 뜻입니다. 마이그레이션은 파일 복사로 끝납니다.

## MCP 서버

orag는 직접적인 에이전트 통합을 위한 내장 MCP (Model Context Protocol) 서버를 포함합니다.
bash 도구가 필요 없습니다 -- 에이전트가 orag를 네이티브 도구로 호출합니다.

```bash
pip install orag[serve]   # MCP 지원과 함께 설치

orag serve                        # 자율 모드로 시작 (stdio)
orag serve --mode readonly        # 읽기 전용 (CS 봇)
orag serve --mode managed         # 확인과 함께 쓰기 (CS 관리자)
orag serve --mode autonomous      # 전체 액세스 (개인 비서)
```

### 에이전트 설정

```json
// Claude Code (.mcp.json) / Cursor (.cursor/mcp.json)
{
  "mcpServers": {
    "orag": { "command": "orag", "args": ["serve"] }
  }
}
```

```jsonc
// OpenCode (opencode.jsonc)
{
  "mcp": {
    "orag": { "type": "local", "command": ["orag", "serve"] }
  }
}
```

### 세 가지 모드

| 모드 | 도구 | 사용 사례 |
|------|-------|----------|
| `readonly` | search, get, tree, status, lint | CS 봇 -- KB에서 질문에 답변 |
| `managed` | + learn, edit, meta, forget (확인 포함) | CS 관리자 -- 지식 큐레이션 |
| `autonomous` | + learn, edit, meta, forget (즉시) | 개인 비서 -- 전체 제어 |

### 작동 방식

1. 에이전트가 `orag://index` 리소스를 읽어 KB 구조 파악
2. `search`를 사용하여 관련 항목 검색
3. `get`을 사용하여 전체 내용 읽기 (크기 인식을 위한 문자 수 포함)
4. 쓰기 모드에서: 필요에 따라 항목 생성, 편집, 보관
5. `_index.md`는 모든 변경 후 자동 갱신

## 에이전트 개발자를 위한 안내

orag는 bash 또는 MCP를 통해 LLM 에이전트에서 호출되도록 설계되었습니다. 일반적인 CLI 워크플로우:

```bash
# 에이전트가 무언가를 기억하려 할 때
orag search "관련 키워드"                     # 중복 확인
orag learn "사실" -t "제목" -c cat \
  --tags "t1,t2" --aliases "a1,a2"            # 새로운 경우 저장

# 에이전트가 기억을 되살릴 때
orag search "query" --json                    # 구조화된 결과
orag get "category/file.md" --json            # 문자 수와 함께 전체 내용

# 에이전트가 지식을 업데이트할 때
orag edit "category/file.md" --line 5 "수정된 정보"
orag meta "category/file.md" --add-tags "verified"
```

모든 명령은 성공 시 종료 코드 0, 실패 시 0이 아닌 코드를 반환합니다. `--json` 출력은 항상 유효한 JSON입니다.

## 로드맵

- [x] 핵심 CLI (search, learn, get, edit, meta, forget, tree, status, lint)
- [x] MCP 서버 (`orag serve`) 세 가지 모드 포함
- [x] KB 탐색을 위한 자동 생성 `_index.md`
- [ ] 구조화된 데이터 테이블 (`orag db exec/query/schema`)
- [ ] 문서 & URL 추출 유틸리티 (`orag learn-util`)
- [ ] 자기 진화 지식 (자동 병합, 자동 분할, 오래됨 감지)
- [ ] 웹 UI (`orag web`)

## 라이선스

[MIT](LICENSE)
