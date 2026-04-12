# Storage Design

## Directory Structure

```
{data_dir}/                          설정 가능한 루트 경로 (default: ~/.superpikachu)
│
├── wiki/                            Layer 2: LLM이 작성/관리하는 지식
│   ├── _router.md                   카테고리 맵
│   ├── _log.md                      시간순 이벤트 기록
│   ├── {category}/
│   │   ├── _index.md                폴더 요약 + 파일 목록
│   │   └── {topic}.md               지식 본체
│   └── archive/                     만료/비활성 지식
│       └── {category}/
│           └── {topic}.md
│
├── raw/                             Layer 1: 불변 원본
│   ├── documents/                   업로드된 파일
│   ├── urls/                        크롤링한 웹페이지
│   └── conversations/               대화 로그 (선택)
│
├── _meta.db                         Layer 3: SQLite
├── _schema_history.jsonl            DDL 변경 이력 (백업용)
├── config.toml                      시스템 설정
└── backups/                         자동 백업
    └── _meta.db.2026-04-05.bak
```

## MD 파일 형식

### _router.md (카테고리 맵)

시스템이 자동으로 유지. learn_fact에서 새 카테고리 생성 시 자동 갱신.

```markdown
# Knowledge Router

카테고리 목록과 설명. 검색 시 쿼리와 BM25 매칭하여 카테고리를 결정한다.

## programming
프로그래밍 언어, 개발 도구, 알고리즘, 소프트웨어 엔지니어링 관련 지식.
키워드: python, javascript, typescript, go, rust, git, docker, api, database

## personal
개인 선호, 습관, 목표, 일정, 건강 관련 정보.
키워드: 선호, 취미, 목표, 일정, 건강, 습관

## projects
진행 중인 프로젝트, 업무, 작업 기록.
키워드: 프로젝트, 작업, 마감, 진행, 계획

## research
연구 주제, 논문, 기술 분석, 비교 자료.
키워드: 연구, 논문, 분석, 비교, 트렌드
```

### _index.md (폴더 요약)

각 카테고리 폴더에 존재. 시스템이 자동 유지.

```markdown
# Programming Index

이 카테고리의 파일 목록과 요약.

| 파일 | 키워드 | 설명 | 리콜 수 | 최종 갱신 |
|------|--------|------|---------|----------|
| python-basics.md | python, 변수, 리스트, 함수 | Python 기초 문법 | 47 | 2026-04-05 |
| git-workflow.md | git, branch, merge, pr | Git 워크플로우 | 12 | 2026-04-03 |
| api-design.md | rest, graphql, api, endpoint | API 설계 원칙 | 8 | 2026-04-02 |

총 파일: 3개 | 총 크기: 15.2KB
```

### _log.md (이벤트 로그)

시간순 append-only. Karpathy의 log.md 패턴.
grep으로 파싱 가능한 일관된 포맷 사용.

```markdown
# Knowledge Log

## [2026-04-05 14:30] learn | Python 리스트 컴프리헨션
- category: programming
- source: conversation
- path: wiki/programming/python-basics.md
- conflict: none

## [2026-04-05 14:35] learn_url | Kubernetes 공식 문서
- url: https://kubernetes.io/docs/concepts/overview/
- raw: raw/urls/2026-04-05_kubernetes-overview.md
- path: wiki/devops/kubernetes.md

## [2026-04-05 15:00] conflict_resolved | Vim vs VS Code
- conflict_id: 1
- resolution: "VS Code로 전환, Vim은 이전 사용"
- path: wiki/personal/dev-environment.md

## [2026-04-05 15:10] db_ddl | CREATE TABLE projects
- sql: CREATE TABLE projects (id TEXT PRIMARY KEY, ...)
- created_by: llm

## [2026-04-05 16:00] lint | 건강 체크
- conflicts_pending: 0
- stale: 3
- expired: 1
- suggestions: 2
```

### 지식 파일 (topic.md)

LLM이 작성하는 지식 본체. frontmatter + 내용.

```markdown
---
title: Python 리스트 컴프리헨션
category: programming
tags: [python, list, syntax, comprehension]
source: conversation
created: 2026-04-05T14:30:00Z
updated: 2026-04-05T14:30:00Z
entity_type: concept
temporal_expiry: null
---

# Python 리스트 컴프리헨션

리스트 컴프리헨션은 기존 리스트에서 새 리스트를 간결하게 만드는 Python 문법이다.

## 기본 문법

```python
[expression for item in iterable if condition]
```

## 예시

```python
squares = [x**2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
```

## 중첩 컴프리헨션

```python
matrix = [[1,2,3], [4,5,6]]
flat = [x for row in matrix for x in row]
```

## 관련 지식
- [[python-basics]] - Python 기초 문법
- [[python-generators]] - 제너레이터 표현식과의 차이
```

### 엔티티 타입별 권장 구조 (bluewater 교훈)

**concept** (개념):
```
# {제목}
## 정의
## 핵심 특징
## 예시
## 관련 지식
```

**person** (인물):
```
# {이름}
## 기본 정보
## 관계
## 주요 활동
## 관련 지식
```

**project** (프로젝트):
```
# {프로젝트명}
## 개요
## 기술 스택
## 현재 상태
## 주요 결정 사항
## 관련 지식
```

**event** (이벤트):
```
# {이벤트명}
## 일시/장소
## 내용
## 결과/영향
## 관련 지식
```

**reference** (참고 자료):
```
# {제목}
## 출처
## 요약
## 핵심 인사이트
## 관련 지식
```

## SQLite Schema

### 시스템 테이블 (보호됨)

```sql
-- FTS5 전문 검색 인덱스
-- wiki/ 의 모든 MD 파일 내용을 색인
CREATE VIRTUAL TABLE _knowledge USING fts5(
  path,              -- "programming/python-basics.md"
  category,          -- "programming"
  title,             -- "Python 리스트 컴프리헨션"
  content,           -- 파일 전체 텍스트
  tags,              -- "python,list,syntax"
  entity_type,       -- "concept"
  tokenize='unicode61'
);

-- 파일 변경 추적 (재인덱싱 판단용)
CREATE TABLE _file_index (
  path TEXT PRIMARY KEY,
  hash TEXT NOT NULL,           -- 파일 내용 SHA256
  size INTEGER NOT NULL,
  mtime INTEGER NOT NULL,       -- 마지막 수정 시간
  indexed_at INTEGER NOT NULL   -- 마지막 인덱싱 시간
);

-- 리콜 추적 (사용 빈도)
CREATE TABLE _recalls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  knowledge_path TEXT NOT NULL,    -- "programming/python-basics.md"
  section TEXT,                    -- "## 리스트 컴프리헨션"
  query_hash TEXT NOT NULL,        -- SHA1 12자
  query_text TEXT,                 -- 원본 쿼리 (디버깅용)
  score REAL NOT NULL,             -- BM25 점수
  recalled_at INTEGER NOT NULL     -- Unix timestamp
);

-- 리콜 집계 뷰 (성능용)
CREATE VIEW _recall_stats AS
SELECT
  knowledge_path,
  COUNT(*) as recall_count,
  COUNT(DISTINCT query_hash) as unique_queries,
  AVG(score) as avg_score,
  MAX(recalled_at) as last_recalled,
  MIN(recalled_at) as first_recalled
FROM _recalls
GROUP BY knowledge_path;

-- 충돌 로그
CREATE TABLE _conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  knowledge_path_a TEXT NOT NULL,
  knowledge_path_b TEXT NOT NULL,
  snippet_a TEXT,
  snippet_b TEXT,
  conflict_type TEXT NOT NULL,     -- "contradiction" | "duplicate" | "supersede"
  status TEXT NOT NULL DEFAULT 'pending',  -- "pending" | "resolved" | "ignored"
  resolution TEXT,                 -- 해결 내용 (resolved인 경우)
  created_at INTEGER NOT NULL,
  resolved_at INTEGER
);

-- DDL 변경 이력
CREATE TABLE _schema_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sql_text TEXT NOT NULL,
  table_name TEXT,
  action TEXT NOT NULL,            -- "CREATE" | "ALTER" | "DROP"
  created_by TEXT DEFAULT 'llm',
  executed_at INTEGER NOT NULL,
  success BOOLEAN NOT NULL
);

-- 카테고리 메타데이터
CREATE TABLE _categories (
  name TEXT PRIMARY KEY,
  description TEXT,
  parent TEXT,                     -- 계층 구조 (상위 카테고리)
  doc_count INTEGER DEFAULT 0,
  total_size INTEGER DEFAULT 0,
  created_at INTEGER NOT NULL,
  last_updated INTEGER NOT NULL
);
```

### LLM 생성 테이블 (자유)

LLM이 db_execute로 자유롭게 생성.
유일한 제약: 테이블 이름에 `_` 접두어 불가 (시스템 테이블과 구분).

예시 (LLM이 만들 수 있는):
```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  language TEXT,
  status TEXT DEFAULT 'active',
  priority TEXT,
  started_at TEXT,
  md_path TEXT,                    -- wiki/ 파일 경로 참조
  CONSTRAINT valid_status CHECK (status IN ('active','paused','done','archived'))
);

CREATE TABLE deadlines (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  description TEXT NOT NULL,
  due_date TEXT NOT NULL,
  status TEXT DEFAULT 'active',
  md_path TEXT
);

CREATE TABLE contacts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT,
  company TEXT,
  last_contact TEXT,
  md_path TEXT
);
```

## Safety Mechanisms

### DB 보호
1. 시스템 테이블(`_` 접두어)에 대한 DROP, TRUNCATE, ALTER → 차단 (에러 반환)
2. 시스템 테이블에 INSERT/UPDATE/DELETE → 차단
3. LLM 테이블에 DROP → 허용하되 _schema_log에 기록
4. 모든 DDL → _schema_log + _schema_history.jsonl에 이중 기록
5. config.backup_before_ddl=true일 때 DDL 실행 전 DB 자동 백업

### MD 보호
1. raw/ 디렉토리 → learn_document/learn_url만 쓸 수 있음. 수정/삭제 불가
2. wiki/ 디렉토리 → LLM이 자유롭게 쓰기
3. _router.md, _index.md → 시스템이 갱신 (LLM도 knowledge_reorganize로 간접 수정 가능)
4. _log.md → append-only (수정/삭제 불가)

### 자동 백업
1. 매일 _meta.db 스냅샷 → backups/
2. DDL 변경 전 스냅샷
3. 보관 기간 설정 가능 (default: 30일)

### 스케일 대응
1. 단일 MD 파일: 100KB 상한 → lint에서 분할 권고
2. 폴더당 파일 수: 200개 상한 → lint에서 서브카테고리 권고
3. FTS5: 수백만 행, 수 GB 텍스트도 밀리초 검색
4. WAL 모드: 동시 읽기/쓰기 성능
5. 주기적 VACUUM: lint에서 트리거
6. 대규모 시 카테고리별 DB 샤딩 가능 (향후)
