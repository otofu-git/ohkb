# Architecture

English: [ARCHITECTURE.md](ARCHITECTURE.md)

## Overview

ohkb는 계층형 4-레이어 아키텍처로 구성된다.
CLI와 MCP 서버 모두 `KnowledgeBase` 서비스 레이어만 호출한다 — 레이어를 건너뛰지 않는다.

```
┌─────────────────────────────────────────────────────────┐
│                    LLM 에이전트                           │
│           Claude / GPT / Llama / Gemini / ...            │
└──────────────────┬──────────────────────────────────────┘
                   │ MCP Protocol (로컬 stdio)
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────┐    ┌──────────────────┐
│  CLI (cli.py)│    │ MCP Server       │
│  Click 커맨드 │    │ (serve.py)       │
│  직접 사용자  │    │ FastMCP tools    │
└──────┬───────┘    └────────┬─────────┘
       │                     │
       └──────────┬──────────┘
                  ▼
     ┌────────────────────────┐
     │  KnowledgeBase (kb.py) │  ← 서비스 레이어 (단일 진입점)
     │  search / get / tree   │
     │  learn / edit / meta   │
     │  forget / restore      │
     │  reindex / status/lint │
     └────────┬───────────────┘
              │
    ┌─────────┴──────────┐
    ▼                    ▼
┌──────────┐    ┌────────────────┐
│ wiki.py  │    │  store.py      │
│ MD 파일   │    │  SQLite FTS5   │
│ 읽기/쓰기 │    │  BM25 검색     │
└──────────┘    └────────────────┘
    ▲                    ▲
    └─────────┬──────────┘
              ▼
  ┌───────────────────────┐
  │ models.py + config.py │  ← 기반 레이어
  │ Entry dataclass        │
  │ OHKB_DIR 경로 설정     │
  └───────────────────────┘
```

## 레이어별 역할

### 1. Presentation Layer (cli.py / serve.py)

**규칙**: `KnowledgeBase`만 호출한다. `wiki.py`나 `store.py`를 직접 호출하지 않는다.

**cli.py** — Click 기반 CLI
- 모든 커맨드(`search`, `learn`, `get`, `edit`, `meta`, `forget`, `tree`, `status`, `lint`, `serve`)
- 에러를 `stderr`에 출력하고 `SystemExit(1)` 발생
- `--json` 플래그로 구조화된 출력 지원
- `serve` 커맨드는 `ohkb.serve`를 lazy import (MCP 의존성 선택적)

**serve.py** — FastMCP 기반 MCP 서버
- 3가지 모드: `readonly`, `managed`, `autonomous`
- 읽기 툴 (전 모드): `search`, `get`, `tree`, `status`, `lint`
- 쓰기 툴 (`managed`/`autonomous`): `learn`, `edit`, `meta`, `forget`
- 리소스: `ohkb://index` (검색 색인에서 만든 KB 개요)
- 프롬프트: `research`, `learn_from_text`, `organize`
- 모든 쓰기 후 `invalidate_index()` 호출(`_index.md` 삭제, 읽을 때 SQLite로 다시 만듦)

### 2. Service Layer (kb.py)

**규칙**: 모든 뮤테이션은 파일시스템 먼저, 그 다음 FTS5 인덱스 업데이트.

`KnowledgeBase` 클래스가 `Store`를 소유하고 `wiki.py`에 파일시스템 작업을 위임한다.

```python
# 이중 쓰기 패턴 (모든 뮤테이션)
save_entry(entry, overwrite=overwrite)  # 파일시스템 먼저
self._store.upsert(entry)               # 그 다음 FTS5
```

| 메서드 | 설명 |
|--------|------|
| `search(query, category, limit)` | FTS5 BM25 전문 검색 |
| `get(path)` | 줄 번호/문자수 포함 파일 읽기 |
| `tree(path, depth)` | 위키 구조 탐색 |
| `status()` | 통계 (인덱스 수, 파일 수, in_sync, 카테고리) |
| `lint()` | 건강 체크 (drift, 크기, 태그, frontmatter) |
| `reindex()` | 디스크 → FTS 전체 재구축 |
| `learn(...)` | 새 엔트리 저장 (이중 쓰기) |
| `edit(path, ...)` | 줄 레벨 편집 후 재인덱싱 (frontmatter 보호) |
| `meta(path, ...)` | 메타데이터 업데이트, 경로 변경 시 파일 재배치 |
| `forget(path, reason)` | 아카이브 이동 + 인덱스에서 삭제 (버전 보존) |
| `restore(...)` | 아카이브 → wiki 복원 + 재인덱싱 |

### 3. Data Layer (wiki.py + store.py)

**wiki.py** — 파일시스템 작업
- `save_entry`: YAML frontmatter + 본문을 MD로 직렬화하여 저장 (`mkdir -p` 자동)
- `read_entry` / `read_file_lines`: 파일 읽기
- `edit_line` / `edit_lines` / `insert_after` / `delete_line`: 줄 레벨 편집
- `archive_entry`: 타임스탬프 HTML 주석 추가 후 `archive/`로 이동, 빈 부모 디렉토리 재귀 정리
- `build_tree`: 깊이 제한 재귀 트리 생성
- `update_frontmatter`: 메타데이터 업데이트, 카테고리 변경 시 파일 이동 + 빈 디렉토리 정리

**store.py** — SQLite FTS5 색인
- `entries` 테이블 (primary): path, title, category, tags, aliases, entity_type, source, created, updated, content + 검색 토큰 4열(`*_tokens`)
- `entries_fts` 가상 테이블 (FTS5): `*_tokens` 열을 `content=entries`로 색인, 3개 트리거(INSERT/DELETE/UPDATE)로 동기화
- `search_tokens`: 한글·가나·한자 연속 구간은 두 글자씩 겹쳐 자르고(bigram), 나머지 단어는 소문자 단어 그대로
- `upsert`: 한 트랜잭션에서 DELETE 후 INSERT (`INSERT OR REPLACE`는 삭제 트리거를 실행하지 않아 색인에 이전 행이 남는다)
- `search`: 검색어 토큰을 OR로 묶고 BM25 가중치로 랭킹, 카테고리 prefix LIKE 매칭 지원
- WAL 모드, lazy connection 초기화

### 4. Foundation Layer (models.py + config.py)

**models.py** — `Entry` dataclass
```python
@dataclass
class Entry:
    title: str
    category: str
    content: str
    tags: list[str]
    aliases: list[str]
    entity_type: str       # concept / person / event / project / reference
    source: str            # manual / document / reference
    created: datetime
    updated: datetime

    @property
    def slug(self) -> str: ...     # URL-safe title
    @property
    def filename(self) -> str: ... # "category/slug.md"
    def to_markdown(self) -> str: ...
    @classmethod
    def from_markdown(cls, text: str) -> Entry: ...
```

**config.py** — 경로 설정
- `OHKB_DIR` 환경변수로 데이터 디렉토리 오버라이드 (기본: `~/.ohkb`)
- `get_data_dir()`, `get_wiki_dir()`, `get_archive_dir()`, `get_db_path()`
- 모든 함수는 접근 시 디렉토리 자동 생성

## 데이터 구조

### 파일시스템

```
~/.ohkb/                        # OHKB_DIR로 오버라이드 가능
  _meta.db                      # SQLite: FTS5 인덱스 + 메타데이터
  wiki/
    _index.md                   # 전체 항목 목록 (`ohkb index`가 씀)
    python/
      free-threaded-python.md   # category = "python"
      internals/
        cpython.md              # category = "python/internals" (중첩)
  archive/                      # forget된 파일 (타임스탬프 주석 포함)
```

### SQLite 스키마

```sql
CREATE TABLE entries (
    path        TEXT PRIMARY KEY,   -- "category/slug.md"
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,      -- "python" 또는 "python/internals"
    tags        TEXT NOT NULL,      -- comma-separated
    aliases     TEXT NOT NULL,      -- comma-separated
    entity_type TEXT NOT NULL,
    source      TEXT NOT NULL,
    created     TEXT NOT NULL,
    updated     TEXT NOT NULL,
    content     TEXT NOT NULL,
    -- search_tokens() 결과 (공백 구분). entries_fts는 이 열들을 색인한다.
    title_tokens   TEXT NOT NULL,
    tags_tokens    TEXT NOT NULL,
    aliases_tokens TEXT NOT NULL,
    content_tokens TEXT NOT NULL
);

CREATE VIRTUAL TABLE entries_fts USING fts5(
    title_tokens, tags_tokens, aliases_tokens, content_tokens,
    content=entries,              -- content table 참조
    content_rowid=rowid
);
```

스키마 버전은 2입니다. 0.1.0이 만든 스키마 1 DB는 처음 열 때 토큰 열을 채우고 색인을 다시 만듭니다.

### BM25 가중치

```python
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)
#                title  tags  aliases  content
```

제목 매칭이 가장 강한 신호(10×), 본문 내용이 가장 약함(1×).
SQLite `bm25()` 값은 음수(낮을수록 좋음) → `kb.py`에서 `abs()`로 양수 변환.

### 카테고리 지원 수준

| 작업 | 중첩 경로 지원 |
|------|--------------|
| `learn` (쓰기) | `mkdir -p`로 자동 생성 |
| `tree` (탐색) | `depth` 파라미터로 제어 |
| `search --category` | prefix 매칭 (`python`이 `python/internals`도 포함) |
| `read_entry` / reindex | path parent로 full category 파생 |
| `meta` (title/category) | 파일 재배치 + 구 경로 삭제 |

## 인덱스 자동 생성 (index.py)

`_index.md`는 검색 색인(SQLite)의 전체 항목을 분류별로 나열한 파일이다. 파일을 다시 읽지 않아 수천 개도 수십 ms에 만든다.

- `ohkb index`를 실행하거나 `read_index()`가 파일이 없을 때 만든다.
- 쓰기(`learn`, `edit`, `meta`, `forget`, `restore`, `reindex`) 뒤에는 다시 만들지 않고 지운다(`invalidate_index()`). 낡은 내용이 남지 않고 쓰기 비용이 지식 크기와 무관하다.
- MCP 서버는 시작할 때 만들지 않는다.
- MCP `index` 도구와 `ohkb://index`는 `generate_overview()`를 돌려준다. 전체 목록이 `OVERVIEW_MAX_CHARS`(12,000자) 안이면 그대로, 넘으면 분류별 항목 수와 대표 태그(큰 분류부터), `category`를 주면 그 분류의 항목. 에이전트 호스트가 도구 결과 크기를 제한하므로(Claude Code 약 2.5만 토큰) 수천 개 전체 목록은 실패한다.
- 에이전트는 `index`가 아니라 `search`로 시작한다.

## MCP 서버 모드

```
readonly    → search, get, tree, status, lint
managed     → + learn, edit, meta, forget (프롬프트에 확인 유도 지침 포함)
autonomous  → + learn, edit, meta, forget (즉시 실행)
```

**참고**: `managed` 모드의 확인 강제는 프로그래밍적 게이트가 아닌 LLM 지침(서버 instructions 텍스트)으로 구현된다.

## 테스트 구조

```
tests/
  test_kb.py    # KnowledgeBase 유닛 테스트 (직접 API 호출)
  test_basic.py # CLI 통합 테스트 (CliRunner 사용)
  test_index.py # 인덱스 생성 테스트
```

모든 테스트:
- `autouse=True` fixture로 `OHKB_DIR`을 `tmp_path`로 설정
- 실제 파일시스템 + 실제 SQLite 사용 (모킹 없음)
- `pytest.raises`로 예외 검증
