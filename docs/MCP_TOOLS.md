# MCP Tools Specification

## Design Principle

- 시스템은 LLM을 절대 호출하지 않는다
- LLM이 도구를 호출하고, 결과를 받아서 판단한다
- 모든 도구는 순수 데이터 처리만 수행한다
- LLM이 "이 사실을 저장해" 같은 판단을 해서 넘겨주면, 시스템은 저장/검색/관리만 한다

## Tool Groups

### 1. Knowledge Search Tools (검색)

#### `knowledge_search`
MD 지식 베이스에서 BM25 기반 검색.

```
Input:
  query: string (required)        검색 쿼리
  max_results: integer (optional) 최대 결과 수 (default: 10)
  category: string (optional)     특정 카테고리로 한정
  min_score: float (optional)     최소 BM25 점수 (default: 0.1)

Output:
  results: [
    {
      path: string               "programming/python.md"
      section: string            "## 리스트 컴프리헨션"
      score: float               0.87
      snippet: string            "리스트 컴프리헨션은 [expr for ..."
      recall_count: integer      47
      last_recalled: string      "2026-04-05T10:30:00Z"
    }
  ]
  total_found: integer
  search_strategy: string        "hierarchical" | "fts5_global"
```

내부 동작:
1. category가 지정되면 → 해당 카테고리 내 FTS5 검색
2. category 없으면 → _router.md BM25 매칭으로 카테고리 추론 → _index.md → 파일 내 FTS5
3. 계층적 검색 결과가 부족하면 → 전체 FTS5 폴백
4. 검색 결과마다 _recalls 테이블에 자동 기록 (리콜 추적)

#### `knowledge_get`
특정 MD 파일 또는 섹션을 읽기.

```
Input:
  path: string (required)         "programming/python.md"
  from_line: integer (optional)   시작 줄 번호
  lines: integer (optional)       읽을 줄 수

Output:
  content: string                 파일/섹션 텍스트
  total_lines: integer
  file_size: integer              bytes
```

#### `knowledge_tree`
지식 베이스의 폴더/파일 구조 조회.

```
Input:
  depth: integer (optional)       트리 깊이 (default: 2)
  category: string (optional)     특정 카테고리만

Output:
  tree: {
    categories: [
      {
        name: string              "programming"
        description: string       "프로그래밍 언어, 도구, 알고리즘"
        file_count: integer       12
        total_size: integer       bytes
        children: [
          { name: "python.md", size: 4521, recall_count: 47 },
          { name: "git.md", size: 2103, recall_count: 12 }
        ]
      }
    ]
    total_files: integer
    total_categories: integer
    total_size: integer
  }
```

#### `knowledge_status`
지식 베이스 건강 상태와 통계 조회.

```
Input: (없음)

Output:
  stats: {
    total_facts: integer
    total_categories: integer
    total_files: integer
    total_size_bytes: integer
  }
  health: {
    conflicts_pending: integer     미해결 충돌 수
    stale_count: integer          30일 이상 미리콜 지식 수
    expired_count: integer        만료된 지식 수
    oversized_files: integer      100KB 초과 파일 수
    orphan_pages: integer         참조 없는 페이지 수
  }
  knowledge_gaps: [               빈 곳 목록
    { category: string, description: string }
  ]
  recall_stats: {
    most_recalled: [{ path, count }]
    least_recalled: [{ path, count }]
    avg_daily_recalls: float
  }
  db_tables: {                    LLM 생성 테이블 통계
    count: integer
    names: [string]
    total_rows: integer
  }
```

### 2. Learning Tools (학습)

#### `learn_fact`
단일 사실/지식을 MD 파일에 저장.

```
Input:
  category: string (required)     "programming" (없으면 자동 생성)
  title: string (required)        "Python 리스트 컴프리헨션"
  content: string (required)      "리스트 컴프리헨션은 간결하게..."
  metadata: object (optional) {
    tags: [string]                ["python", "list", "syntax"]
    source: string                "conversation" | "document" | "url" | "manual"
    source_path: string           원본 파일 경로 (있을 경우)
    temporal_expiry: string       "2026-12-31" (만료일, null이면 영구)
    entity_type: string           "concept" | "person" | "project" | "event" | "reference"
  }

Output:
  path: string                    "programming/python-list-comprehension.md"
  created: boolean                true (새 파일) / false (기존 파일에 append)
  conflict: object | null {       충돌 발견 시
    conflict_id: integer
    existing_path: string
    existing_snippet: string
    conflict_type: string         "contradiction" | "duplicate" | "supersede"
  }
```

내부 동작:
1. wiki/{category}/ 폴더 확인, 없으면 생성 + _index.md 생성 + _router.md 갱신
2. 적절한 파일에 내용 추가 (제목 기반 기존 파일 매칭 또는 새 파일)
3. _knowledge FTS5 인덱스 갱신
4. _index.md 갱신
5. 기존 지식과 키워드 겹침 검사 → 충돌 감지
6. _log.md에 이벤트 기록
7. 충돌 있으면 _conflicts 테이블에 기록하고 결과에 포함

#### `learn_document`
문서 파일의 텍스트를 추출하여 반환. 분류/저장은 LLM이 판단.

```
Input:
  file_path: string (required)    로컬 파일 경로 또는 업로드 경로

Output:
  raw_path: string                "raw/documents/api-design.pdf"
  extracted_text: string          추출된 전체 텍스트
  page_count: integer             (PDF 등의 경우)
  file_type: string               "pdf" | "docx" | "xlsx" | "txt" | ...
  file_size: integer              원본 파일 크기 (bytes)
```

지원 파일 형식:
- 텍스트: MD, TXT, CSV, TSV, JSON, YAML, TOML, XML
- 문서: PDF, DOCX, XLSX, PPTX, RTF, ODT
- 웹: HTML → MD 변환
- 코드: 모든 프로그래밍 언어 (텍스트로 처리)
- 이미지: OCR (tesseract 등 로컬 라이브러리)
- 오디오: whisper (로컬) → 트랜스크립트
- 비디오: 오디오 트랙 추출 → whisper → 트랜스크립트

#### `learn_url`
URL의 웹페이지를 크롤링하여 텍스트 추출 후 반환.

```
Input:
  url: string (required)

Output:
  raw_path: string                "raw/urls/2026-04-05_kubernetes-overview.md"
  extracted_text: string          크롤링/변환된 텍스트
  title: string                   페이지 제목
  domain: string                  "kubernetes.io"
  fetched_at: string              ISO timestamp
```

### 3. Management Tools (관리)

#### `knowledge_update`
기존 지식의 내용을 수정.

```
Input:
  path: string (required)         "programming/python.md"
  section: string (optional)      "## 리스트 컴프리헨션" (특정 섹션만)
  new_content: string (required)  수정된 내용

Output:
  updated: boolean
  previous_content: string        수정 전 내용 (되돌리기용)
```

#### `knowledge_merge`
충돌하는 두 지식을 병합.

```
Input:
  conflict_id: integer (required) _conflicts 테이블의 ID
  resolution: string (required)   LLM이 결정한 병합 내용
  keep: string (optional)         "newer" | "older" | "both" | "custom"

Output:
  merged_path: string
  old_a: string                   충돌 항목 A의 원본
  old_b: string                   충돌 항목 B의 원본
  resolved: boolean
```

#### `knowledge_forget`
지식을 archive/로 이동 (삭제가 아닌 아카이브).

```
Input:
  path: string (required)         "personal/old-address.md"
  reason: string (optional)       "이사함, 이전 주소 불필요"

Output:
  archived_path: string           "archive/personal/old-address.md"
  removed_from_index: boolean
```

#### `knowledge_reorganize`
지식 구조를 재편.

```
Input:
  action: string (required)       "split_file" | "merge_files" | "move_category" | 
                                  "create_category" | "rename"
  params: object (required) {
    // action별 다른 파라미터
    // split_file: { path, sections }
    // merge_files: { paths, target_path }
    // move_category: { path, new_category }
    // create_category: { name, description, parent? }
    // rename: { old_path, new_path }
  }

Output:
  changes: [
    { action: string, from: string, to: string }
  ]
  index_updated: boolean
  router_updated: boolean
```

#### `knowledge_lint`
지식 베이스 건강 체크. 문제점과 개선 제안 반환.

```
Input: (없음)

Output:
  contradictions: [{ conflict_id, path_a, path_b, snippet_a, snippet_b }]
  orphans: [{ path, reason }]
  stale: [{ path, last_recalled, days_since }]
  expired: [{ path, expiry_date }]
  oversized: [{ path, size_bytes, recommended_action }]
  gaps: [{ category, description }]
  suggestions: [{ type, description, action }]
```

### 4. DB Tools (LLM 자유 스키마)

#### `db_execute`
SQL 실행 (DDL + DML). 시스템 테이블은 보호.

```
Input:
  sql: string (required)          SQL문 (CREATE, INSERT, UPDATE, DELETE, ALTER 등)
  params: array (optional)        바인드 파라미터

Output:
  affected_rows: integer
  result: string                  실행 결과 메시지
  schema_logged: boolean          DDL인 경우 true (자동 이력 기록)
```

제약 사항:
- 시스템 테이블(`_`접두어)에 대한 DROP, TRUNCATE, ALTER 차단
- 시스템 테이블에 INSERT/UPDATE/DELETE도 차단 (읽기만 허용)
- 모든 DDL은 _schema_log에 자동 기록
- 트랜잭션 크기 제한: 한 번에 10,000행 이상 변경 시 경고

#### `db_query`
SELECT 쿼리 실행.

```
Input:
  sql: string (required)          SELECT문
  params: array (optional)        바인드 파라미터
  limit: integer (optional)       결과 수 제한 (default: 100)

Output:
  columns: [string]               컬럼 이름 목록
  rows: [array]                   결과 행 목록
  row_count: integer
  truncated: boolean              limit로 잘린 경우 true
```

#### `db_schema`
현재 데이터베이스 스키마 조회.

```
Input:
  table: string (optional)        특정 테이블만 조회

Output:
  tables: [
    {
      name: string
      columns: [{ name, type, nullable, default_value, primary_key }]
      row_count: integer
      created_by: string          "system" | "llm"
      created_at: string
      last_modified: string
    }
  ]
  schema_version: integer
  last_ddl_change: string
```

### 5. Config Tools (설정)

#### `config_get`
```
Input:
  key: string (optional)          특정 설정 키. 없으면 전체 설정 반환

Output:
  config: object
```

#### `config_set`
```
Input:
  key: string (required)
  value: any (required)

Output:
  updated: boolean
  previous_value: any
```

설정 가능 항목 (config.toml):
- `data_dir`: 데이터 루트 경로
- `max_file_size`: MD 파일 크기 상한 (default: 100KB)
- `max_files_per_category`: 카테고리당 파일 수 상한 (default: 200)
- `stale_threshold_days`: 부실 판정 기준일 (default: 30)
- `auto_archive_expired`: 만료 지식 자동 아카이브 (default: true)
- `backup_before_ddl`: DDL 변경 전 자동 백업 (default: true)
- `web_ui_port`: Web UI 포트 (default: 7777)
