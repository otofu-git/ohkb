# Implementation Status

구현 현황. 설계 문서 대비 실제 구현된 코드의 상태.

## Project Structure (구현 완료)

```
superpikachu/
├── pyproject.toml
├── ecosystem.config.js              pm2 설정
├── seed.py                          데모 데이터 시딩
│
├── src/superpikachu/
│   ├── __init__.py
│   ├── config.py                    TOML 설정 로더
│   ├── constants.py                 상수 (경로, 임계값 등)
│   │
│   ├── storage/
│   │   ├── database.py              SQLite 연결/초기화/WAL/시스템테이블 보호
│   │   ├── wiki.py                  wiki/ MD 파일 CRUD + frontmatter + 카테고리
│   │   ├── indexer.py               FTS5 인덱싱 + 파일 해시 변경 추적
│   │   ├── router_md.py             _router.md 자동 생성/갱신
│   │   ├── index_md.py              카테고리별 _index.md 자동 생성
│   │   ├── log_md.py                _log.md append-only 이벤트 기록
│   │   ├── raw.py                   raw/ 원본 파일 보존
│   │   └── models.py               SearchResult, WriteResult, ConflictInfo, TreeNode
│   │
│   ├── search/
│   │   ├── engine.py                통합 검색 (계층적 → FTS5 폴백)
│   │   ├── hierarchical.py          _router.md 기반 카테고리 매칭 → FTS5
│   │   ├── fts.py                   전역 FTS5 검색 + bm25 가중치
│   │   ├── recall.py                리콜 기록/집계/점수 부스트
│   │   └── conflict.py              충돌 감지 (키워드 겹침) + 해결
│   │
│   ├── mcp/
│   │   ├── server.py                FastMCP 엔트리포인트 (stdio)
│   │   ├── tools_knowledge.py       search/get/tree/status/lint (5개)
│   │   ├── tools_learn.py           fact/document/url (3개)
│   │   ├── tools_manage.py          update/merge/forget/reorganize (4개)
│   │   ├── tools_db.py              execute/query/schema (3개)
│   │   └── tools_config.py          get/set (2개)
│   │
│   ├── api/
│   │   └── app.py                   FastAPI REST API + 정적 파일 서빙
│   │
│   ├── extract/                     (스텁, learn_document에서 인라인 처리 중)
│   └── cli/
│       └── main.py                  Click CLI (brain serve/search/status/tree/init/db)
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html                   Inter 폰트 로딩
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                  메인 레이아웃 (graph/timeline/stats 탭)
│   │   ├── lib/
│   │   │   ├── api.ts               fetch 기반 REST 클라이언트
│   │   │   ├── theme.ts             다크 테마 색상 + 노드 크기/투명도 계산
│   │   │   └── types.ts             GraphNode, GraphEdge, Cluster, ViewMode 등
│   │   ├── hooks/
│   │   │   └── useGraphData.ts      /api/graph 폴링 (8초 주기)
│   │   └── components/
│   │       ├── GraphView.tsx         react-force-graph-3d + bloom + glow sprite
│   │       ├── Toolbar.tsx           4개 모드 버튼 + KPI 카드
│   │       ├── SearchBar.tsx         실시간 검색 + 드롭다운
│   │       ├── SidePanel.tsx         노드 클릭 → MD 렌더링 + 메타
│   │       ├── Timeline.tsx          이벤트 로그 (타입별 색상/아이콘)
│   │       └── StatsPanel.tsx        통계 카드 + LLM/시스템 테이블 목록
│   └── dist/                        빌드 산출물 (FastAPI가 정적 서빙)
│
└── tests/
    ├── test_e2e.py                  MCP 도구 시뮬레이션 E2E (58/58 pass)
    ├── test_llm_e2e.py              실제 Claude API E2E (14/14 pass)
    ├── test_llm_verbose.py          Claude 대화 전문 로깅 버전
    └── test_frontend.py             Playwright headless 브라우저 테스트
```

## Dependencies (구현 완료)

### Python
```
mcp>=1.0          MCP SDK (FastMCP)
httpx>=0.27       HTTP 클라이언트 (learn_url)
beautifulsoup4    HTML 파싱
markdownify       HTML → MD 변환
click>=8.1        CLI
fastapi>=0.115    REST API
uvicorn>=0.30     ASGI 서버
anthropic>=0.89   LLM E2E 테스트용 (선택)
playwright        프론트엔드 E2E 테스트용 (선택)
```

yaml 의존성 제거 — frontmatter를 직접 파싱하여 표준 라이브러리만으로 동작.

### Frontend
```
react-force-graph-3d    3D 그래프 (Three.js 기반)
three                   WebGL 렌더링
recharts                통계 차트 (미사용, 향후)
gsap                    애니메이션 (미사용, 향후)
react-markdown          MD 렌더링 (SidePanel)
```

## MCP Tools (17개 구현 완료)

| 그룹 | 도구 | 상태 |
|------|------|------|
| 검색 | knowledge_search | 구현 완료 |
| | knowledge_get | 구현 완료 |
| | knowledge_tree | 구현 완료 |
| | knowledge_status | 구현 완료 |
| | knowledge_lint | 구현 완료 |
| 학습 | learn_fact | 구현 완료 |
| | learn_document | 구현 완료 (텍스트/PDF/DOCX/HTML) |
| | learn_url | 구현 완료 (httpx + BS4 + markdownify) |
| 관리 | knowledge_update | 구현 완료 |
| | knowledge_merge | 구현 완료 |
| | knowledge_forget | 구현 완료 (archive 이동) |
| | knowledge_reorganize | 부분 구현 (create_category만) |
| DB | db_execute | 구현 완료 (DDL+DML, 시스템 테이블 보호) |
| | db_query | 구현 완료 (SELECT/PRAGMA만) |
| | db_schema | 구현 완료 |
| 설정 | config_get | 구현 완료 |
| | config_set | 스텁 (런타임만, 파일 미반영) |

## REST API (구현 완료)

| 엔드포인트 | 메서드 | 용도 |
|-----------|--------|------|
| /api/graph | GET | 시각화 데이터 (nodes, edges, clusters) |
| /api/search?q= | GET | BM25 검색 |
| /api/knowledge/{path} | GET | MD 파일 읽기 |
| /api/tree | GET | 지식 구조 트리 |
| /api/stats | GET | 통계 + 건강 상태 |
| /api/timeline | GET | 이벤트 로그 |
| /api/conflicts | GET | 미해결 충돌 목록 |
| /api/db/tables | GET | DB 테이블 목록 |
| /api/db/query | POST | SQL SELECT 실행 |
| / | GET | 프론트엔드 정적 파일 서빙 |

## Frontend (구현 완료)

| 컴포넌트 | 상태 | 기능 |
|---------|------|------|
| GraphView | 구현 | react-force-graph-3d, bloom, glow sprite, conflict ring |
| Toolbar | 구현 | 4개 모드 버튼, KPI 카드 (files/categories/recalls/conflicts) |
| SearchBar | 구현 | 실시간 BM25 검색, 결과 드롭다운 |
| SidePanel | 구현 | 노드 클릭 → MD 렌더링 + 메타데이터 태그 |
| Timeline | 구현 | 이벤트 로그, 타입별 색상/아이콘, 날짜 그룹핑 |
| StatsPanel | 구현 | 통계 카드, LLM/시스템 테이블 목록 |

### 모드 전환
- Constellation: 카메라 정면 고정 (2D처럼)
- Galaxy: 카메라 자유 회전 + auto-rotate
- Heatmap/Structure: 버튼 존재, 좌표 재배치 미구현

## 검색 엔진 (구현 완료)

### BM25 가중치 설정
```sql
bm25(_knowledge, 1.0, 1.0, 5.0, 10.0, 3.0, 0.0)
-- path=1, category=1, title=5, content=10, tags=3, entity_type=0
```

### 점수 정규화
FTS5의 bm25()가 극소 음수를 반환하는 문제 해결:
```python
raw = abs(bm25_score)
score = max(raw * 1e5, 1.0) if raw > 0 else 0
```
문서 수가 적을 때도 의미 있는 점수가 나오도록 보정.

### 리콜 부스트
```python
score * (1 + log1p(recall_count) * 0.1)
```

## 구현 중 발견/해결한 문제

### 1. yaml 의존성 문제
환경에 pyyaml이 없어서 frontmatter 생성/파싱을 순수 문자열 처리로 변경.

### 2. SQLite 스레드 안전
FastAPI가 스레드풀에서 핸들러를 실행하므로 `check_same_thread=False` 필요.

### 3. MCP SDK API 변경
`mcp.server.Server`에는 `.tool()` 데코레이터가 없음. `FastMCP`로 전환.

### 4. BM25 극소 점수
문서가 적으면 IDF가 0에 수렴하여 bm25 점수가 ~1e-6. 1e5 배율 + 최소 1.0 보정.

### 5. 타임라인 파싱 정규식
`(.+?)` non-greedy가 제목의 첫 글자만 잡는 문제. `(.+)\n`으로 변경.

### 6. 시스템 테이블 보호 누락
DDL 패턴만 체크하고 DML(DELETE FROM _knowledge)은 통과되던 문제.
DML 테이블 파싱 정규식 `_DML_TABLE` 추가.

### 7. Claude의 파라미터 바인딩 실수
`db_execute`에 params를 문자열로 넘겨서 실패 → Claude가 스스로 SQL 직접 삽입으로 복구.
params 타입 검증 강화 고려 필요.

## 미구현 항목

### 백엔드
- [ ] knowledge_reorganize: split_file, merge_files, move_category, rename
- [ ] config_set: config.toml 파일 실제 반영
- [ ] extract/ 모듈 분리 (현재 learn_document에서 인라인)
- [ ] 자동 만료 처리 (temporal_expiry → archive 이동)
- [ ] 자동 백업 (DDL 변경 전, 매일)
- [ ] 대규모 샤딩 (카테고리별 DB 분리)

### 프론트엔드
- [ ] Heatmap 모드 (카테고리 grid 좌표 계산)
- [ ] Structure 모드 (treemap 좌표 계산)
- [ ] 모드 전환 tween 애니메이션 (GSAP)
- [ ] Explorer 뷰 (파일 트리 + MD 편집기)
- [ ] DB Browser (SQL 콘솔 + 테이블 뷰)
- [ ] 파일 업로드 UI
- [ ] 성장 애니메이션 (타임라인 재생)
- [ ] 반응형/모바일 대응

### 테스트
- [ ] 단위 테스트 (pytest)
- [ ] 프론트엔드 컴포넌트 테스트

## 실행 방법

### pm2 (권장)
```bash
pm2 start /home/superpikachu/ecosystem.config.js
pm2 logs superpikachu-web
pm2 stop superpikachu-web
```

### 직접 실행
```bash
PYTHONPATH=/home/superpikachu/src \
SUPERPIKACHU_DATA_DIR=/home/superpikachu/data \
  python3 -m uvicorn superpikachu.api.app:create_app \
  --factory --host 0.0.0.0 --port 7777
```

### MCP 서버 (Claude Code/OpenCode 연결)
```json
{
  "mcpServers": {
    "superpikachu": {
      "command": "python3",
      "args": ["-m", "superpikachu.mcp.server"],
      "env": {
        "PYTHONPATH": "/home/superpikachu/src",
        "SUPERPIKACHU_DATA_DIR": "/home/superpikachu/data"
      }
    }
  }
}
```

### 데모 데이터 시딩
```bash
python3 /home/superpikachu/seed.py
```

### 테스트
```bash
# MCP 도구 E2E (LLM 키 불필요)
PYTHONPATH=/home/superpikachu/src python3 tests/test_e2e.py

# Claude API E2E (키 필요)
ANTHROPIC_API_KEY=sk-... PYTHONPATH=/home/superpikachu/src python3 tests/test_llm_e2e.py

# 프론트엔드 E2E (서버 실행 중이어야 함)
python3 tests/test_frontend.py
```

### 프론트엔드 빌드
```bash
cd frontend && npm run build
```
빌드 산출물은 `frontend/dist/`에 생성되며, FastAPI가 자동으로 정적 서빙.
