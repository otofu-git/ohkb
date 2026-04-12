# Architecture

## Overview

SuperPikachu는 3계층 저장 구조 + 4개 엔진 + 4개 인터페이스로 구성된다.

```
┌───────────────────────────────────────────────┐
│         LLM 에이전트 (어떤 것이든)              │
│   Claude / GPT / Llama / Gemini / ...         │
└──────────────────┬────────────────────────────┘
                   │ MCP Protocol (stdio)
                   ▼
┌───────────────────────────────────────────────┐
│        FastMCP Server (17 tools)               │
│  knowledge_* / learn_* / db_* / config_*      │
└──────────────────┬────────────────────────────┘
                   │
     ┌─────────────┼─────────────┬──────────────┐
     ▼             ▼             ▼              ▼
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Search  │ │ Learning │ │ Organize │ │ Maintain │
│ Engine  │ │ Pipeline │ │ Engine   │ │ Engine   │
└────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │           │            │             │
     └───────────┴────────────┴─────────────┘
                        │
              ┌──────────────────┐
              │  Storage Layer    │
              │  wiki/ + raw/    │
              │  + _meta.db      │
              └──────────────────┘
                        │
     ┌──────────────────┼──────────────────┐
     ▼                  ▼                  ▼
  FastAPI            CLI (brain)       MCP Server
  REST API           search/tree/      (LLM 연결)
  (Web UI용)          status/db
     │
     ▼
  React + Three.js
  (3D 그래프 시각화)
```

### 구현 상태

| 레이어 | 모듈 | 상태 |
|--------|------|------|
| MCP Server | mcp/server.py + tools_*.py | 17개 도구 구현 |
| Search Engine | search/engine.py, hierarchical.py, fts.py | 계층적 BM25 + FTS5 폴백 |
| Learning Pipeline | tools_learn.py + wiki.py + raw.py | fact/document/url |
| Organize Engine | tools_manage.py + wiki.py | update/merge/forget/reorganize(부분) |
| Maintain Engine | tools_knowledge.py (status/lint) + recall.py + conflict.py | 상태/건강체크/리콜/충돌 |
| Storage | storage/*.py | SQLite FTS5 + MD + raw |
| REST API | api/app.py | 10개 엔드포인트 |
| CLI | cli/main.py | serve/search/tree/status/init/db |
| Frontend | frontend/src/*.tsx | Graph/Timeline/Stats + 검색/사이드패널 |

## 3계층 저장 구조

### Layer 1: Raw Sources (불변 원본)

```
raw/
├── documents/      업로드된 PDF, DOCX, TXT 등
├── urls/           크롤링한 웹페이지 (MD 변환)
└── conversations/  대화 로그
```

- **불변**: LLM은 절대 수정하지 않음
- **진실의 원천** (source of truth)
- 모든 지식의 출처를 추적 가능하게 함
- 원본 보존으로 나중에 재처리 가능

### Layer 2: Wiki (LLM이 작성/관리하는 지식)

```
wiki/
├── _router.md            카테고리 맵 (시스템이 유지)
├── _log.md               시간순 이벤트 기록 (append-only)
├── {category}/
│   ├── _index.md         폴더 요약 + 파일 목록 (시스템이 유지)
│   └── {topic}.md        지식 본체 (LLM이 작성)
└── archive/              만료/비활성 지식
```

- **LLM이 소유**: LLM이 작성하고 관리
- **사람도 편집 가능**: MD 파일이므로 어떤 에디터로든
- **_log.md**: Karpathy의 log.md 개념. 시간순 기록. 파싱 가능한 포맷
- **archive/**: 삭제가 아닌 아카이브. 필요시 복구 가능
- **git 추적 권장**: 모든 변경 이력 보존

### Layer 3: Structured Data (SQLite)

```
_meta.db
├── [시스템 테이블] (보호됨, DROP/TRUNCATE 차단)
│   ├── _knowledge      FTS5 전문 검색 인덱스
│   ├── _recalls         리콜 추적 (사용 빈도)
│   ├── _conflicts       충돌 로그
│   ├── _schema_log      DDL 변경 이력
│   └── _file_index      파일 해시/변경 추적
│
└── [LLM 생성 테이블] (자유, 이력만 기록)
    ├── projects         (예시: LLM이 CREATE)
    ├── deadlines        (예시: LLM이 CREATE)
    └── ...              LLM이 필요에 따라 자유롭게 생성/변경
```

- **시스템 테이블**: `_` 접두어. 시스템이 관리. LLM은 읽기만 가능
- **LLM 테이블**: LLM이 DDL(CREATE/ALTER/DROP)까지 자유. 모든 DDL은 `_schema_log`에 자동 기록
- **mpazik 원칙**: "인덱스는 수동 관리 파일이 아니라 쿼리여야 한다"

## 4개 엔진

### 1. Search Engine

임베딩 없이 3가지 전략으로 검색:

| 전략 | 방법 | 적합한 쿼리 | 속도 |
|------|------|-----------|------|
| A: 계층적 BM25 | _router.md → _index.md → FTS5 | "Python 데코레이터 설명" | < 10ms |
| B: SQL 구조 쿼리 | LLM이 db_query로 직접 SQL | "활성 Python 프로젝트 목록" | < 5ms |
| C: 전체 FTS5 | _knowledge 테이블 전체 검색 | 카테고리 모를 때, cross-domain | < 50ms |

LLM이 쿼리 성격을 판단하여 적절한 도구를 선택한다.
상세 설계는 [SEARCH.md](./SEARCH.md) 참조.

### 2. Learning Pipeline

```
learn_fact(category, title, content, metadata)
  ├→ 카테고리 폴더 확인/생성
  ├→ 해당 MD 파일에 append 또는 새 파일 생성
  ├→ FTS5 인덱스 갱신
  ├→ _index.md 갱신
  ├→ 충돌 검사 → _conflicts 테이블 기록
  └→ 충돌 있으면 결과에 포함하여 LLM에게 알림

learn_document(file_path)
  ├→ 파일 타입 감지 + 텍스트 추출 (LLM 불필요)
  ├→ raw/documents/ 에 원본 보존
  └→ 추출된 텍스트를 LLM에게 반환 (분류는 LLM이)

learn_url(url)
  ├→ 웹페이지 크롤링 → MD 변환
  ├→ raw/urls/ 에 원본 보존
  └→ 변환된 텍스트를 LLM에게 반환 (분류는 LLM이)
```

**핵심**: learn_document와 learn_url은 텍스트 추출만 하고 LLM에게 돌려줌. 
분류/요약/지식화는 LLM이 판단하여 learn_fact로 저장.

### 3. Organize Engine

```
자동 카테고리 생성:
  learn_fact에서 새 카테고리 지정 시
  → 폴더 + _index.md 자동 생성
  → _router.md에 카테고리 추가

knowledge_reorganize 액션들:
  - split_file:      큰 파일을 섹션별로 분할
  - merge_files:     관련 파일들을 하나로 합침
  - move_category:   파일을 다른 카테고리로 이동
  - create_category: 새 카테고리 생성
  - rename:          파일/카테고리 이름 변경
```

### 4. Maintain Engine

```
knowledge_lint() 실행 시 검사 항목:
  ├→ 충돌 검사: _conflicts에서 미해결 건
  ├→ 고아 검사: 어디서도 참조되지 않는 페이지
  ├→ 부실 검사: N일 이상 리콜 안 된 지식
  ├→ 만료 검사: temporal_expiry 지난 지식
  ├→ 크기 검사: 100KB 초과 파일 (분할 필요)
  ├→ 빈곳 검사: 카테고리는 있지만 내용 부족
  └→ 결과를 LLM에게 반환 (수정 판단은 LLM이)

리콜 추적 (자동, 백그라운드):
  knowledge_search 호출 시마다
  → _recalls 테이블에 기록
  → 사용 빈도 기반 "중요도" 자동 산출

자동 망각:
  temporal_expiry 만료된 지식
  → archive/로 이동 (삭제가 아닌 아카이브)
  → FTS5 인덱스에서 제거
```

## 3개 인터페이스

### 1. MCP Server (핵심)
- LLM이 호출하는 유일한 접점
- 모든 기능을 MCP 도구로 노출
- 상세 사양은 [MCP_TOOLS.md](./MCP_TOOLS.md) 참조

### 2. CLI Tool
- 관리/디버깅/직접 조작용
- MCP 서버 시작, 검색, 상태 조회, 임포트/익스포트, SQL 실행

### 3. Web UI
- 시각화, 편집, 파일 업로드, 통계 대시보드
- 그래프 뷰, 탐색기 뷰, DB 브라우저, 타임라인, 충돌 해결 UI
- 상세 설계는 [UI.md](./UI.md) 참조

## 데이터 흐름 예시

### 시나리오 1: 대화에서 학습

```
사용자: "나 Python 좋아하고 VS Code 써"
LLM: (이 사실을 저장해야겠다)
LLM → learn_fact(category="personal", title="개발 환경", 
        content="Python 선호, VS Code 사용", 
        metadata={source:"conversation", tags:["dev","editor"]})

시스템:
  1. wiki/personal/ 폴더 확인 (없으면 생성)
  2. wiki/personal/dev-environment.md에 기록
  3. FTS5 인덱스 갱신
  4. 기존 지식에 "Vim 사용" 발견 → 충돌
  5. → LLM에게 반환: {created:true, conflict:{existing:"Vim 사용", new:"VS Code 사용"}}

LLM: (충돌이 있네, 해결하자)
LLM → knowledge_merge(conflict_id=1, resolution="VS Code로 전환함. Vim은 이전에 사용")
```

### 시나리오 2: 문서 흡수

```
사용자: "이 PDF 읽어서 정리해줘"
LLM → learn_document(file_path="/tmp/api-design.pdf")

시스템:
  1. PDF 텍스트 추출
  2. raw/documents/api-design.pdf 원본 보존
  3. → LLM에게 반환: {raw_path:"raw/documents/api-design.pdf", 
                       extracted_text:"...(전체 텍스트)...", 
                       page_count:42, file_type:"pdf"}

LLM: (읽고 분석한 후 여러 번 learn_fact 호출)
LLM → learn_fact(category="programming", title="REST API 설계 원칙", ...)
LLM → learn_fact(category="programming", title="GraphQL vs REST", ...)
```

### 시나리오 3: LLM이 DB 스키마를 스스로 설계

```
(프로젝트 대화가 늘어나자)
LLM: (프로젝트별 추적이 필요하겠다)
LLM → db_execute(sql="CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        language TEXT,
        status TEXT DEFAULT 'active',
        started_at TEXT,
        md_path TEXT
      )")

시스템:
  1. SQL 실행
  2. _schema_log에 DDL 기록
  3. → {affected_rows:0, result:"table created"}

LLM → db_execute(sql="INSERT INTO projects VALUES 
        ('p1','My App','Python','active','2026-04','wiki/projects/my-app.md')")
```

### 시나리오 4: 자율 확장

```
사용자: "Kubernetes 배포 어떻게 해?"
LLM → knowledge_search(query="Kubernetes 배포")
시스템: → {results: []} (결과 없음)

LLM → knowledge_status()
시스템: → {..., knowledge_gaps: [{category:"devops", missing:["kubernetes","docker"]}]}

LLM: (이 분야 지식이 부족하구나, 찾아보자)
LLM → learn_url(url="https://kubernetes.io/docs/concepts/overview/")
시스템: → {extracted_text: "...", title: "Kubernetes Overview"}

LLM → learn_fact(category="devops", title="Kubernetes 개요", ...)
LLM: "정리된 내용을 기반으로 답변드리겠습니다..."
```
