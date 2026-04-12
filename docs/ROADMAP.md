# Implementation Roadmap

## Decided Items

- **언어**: Python (백엔드) + TypeScript/React (프론트엔드)
- **Web UI**: React + Vite + react-force-graph-3d (Three.js)
- **MCP SDK**: FastMCP (mcp 패키지)
- **Wiki 포맷**: `[[wikilink]]` 지원, frontmatter (title/category/tags/source/entity_type/created/updated)
- **프로세스 관리**: pm2

## Undecided Items

- 프로젝트 이름 (SuperPikachu는 코드네임)
- 엔티티 타입별 MD 템플릿 적용 여부
- config.toml 런타임 수정 반영 방식

## Phase Status

### Phase 0: Foundation -- DONE
- [x] Python 프로젝트 초기화 (pyproject.toml, 패키지 구조)
- [x] config.py, constants.py
- [x] SQLite 시스템 테이블 초기화 (WAL 모드)
- [x] 디렉토리 구조 (wiki/, raw/, _meta.db)

### Phase 1: Core MCP Server -- DONE
- [x] FastMCP 서버 (stdio)
- [x] knowledge_search (계층적 BM25 + FTS5 폴백)
- [x] knowledge_get
- [x] learn_fact (저장 + FTS5 인덱싱 + 충돌 검사)
- [x] knowledge_tree
- [x] knowledge_status, knowledge_lint
- [x] _router.md / _index.md / _log.md 자동 생성/갱신
- [x] 리콜 추적
- [x] MCP E2E 테스트 58/58 pass
- [x] Claude API E2E 테스트 14/14 pass

### Phase 2: Learning & Documents -- DONE
- [x] learn_document (MD/TXT/CSV/JSON/YAML/HTML + PDF/DOCX)
- [x] learn_url (httpx + BeautifulSoup + markdownify)
- [x] raw/ 디렉토리 원본 보존
- [x] frontmatter 생성/파싱 (yaml 의존성 없이)

### Phase 3: DB Freedom -- DONE
- [x] db_execute (DDL + DML)
- [x] db_query (SELECT/PRAGMA)
- [x] db_schema
- [x] 시스템 테이블 보호 (DDL + DML 모두)
- [x] _schema_log 자동 기록
- [ ] _schema_history.jsonl 이중 기록
- [ ] DDL 전 자동 백업

### Phase 4: Management -- PARTIAL
- [x] knowledge_update
- [x] knowledge_merge (충돌 해결)
- [x] knowledge_forget (archive 이동)
- [x] knowledge_reorganize (create_category)
- [ ] knowledge_reorganize (split_file, merge_files, move_category, rename)
- [x] knowledge_lint
- [x] knowledge_status
- [ ] 자동 망각 (temporal_expiry 만료 → archive)

### Phase 5: CLI -- PARTIAL
- [x] brain serve (MCP 서버 시작)
- [x] brain search
- [x] brain tree
- [x] brain status
- [x] brain init
- [x] brain db (SQL 실행)
- [ ] brain lint
- [ ] brain import / export
- [ ] brain log / config

### Phase 6: Web UI Core -- DONE
- [x] FastAPI REST API (10개 엔드포인트)
- [x] React + Vite + TypeScript 프로젝트
- [x] Graph 뷰 (react-force-graph-3d + bloom + glow)
- [x] 검색 바 (실시간 드롭다운)
- [x] Side Panel (MD 렌더링 + 메타데이터)
- [x] Timeline 뷰
- [x] Stats 뷰 (KPI 카드 + 테이블 목록)
- [x] Toolbar (모드 버튼 + 통계)
- [x] 다크 테마 + 네온 팔레트
- [x] 프론트엔드 빌드 + FastAPI 정적 서빙
- [x] pm2 ecosystem 설정
- [ ] Explorer 뷰 (파일 트리 + MD 편집)
- [ ] 파일 업로드 UI
- [ ] URL 입력 UI

### Phase 7: Web UI Advanced -- PARTIAL
- [x] Constellation 모드 (카메라 정면 고정)
- [x] Galaxy 모드 (자유 회전 + auto-rotate)
- [ ] Heatmap 모드 (카테고리 grid 좌표)
- [ ] Structure 모드 (treemap 좌표)
- [ ] 모드 전환 tween 애니메이션
- [ ] DB Browser (SQL 콘솔 + 테이블 뷰)
- [ ] MD 편집기 (WYSIWYG)
- [ ] 충돌 해결 UI
- [ ] 성장 애니메이션 (타임라인 재생)
- [ ] 통계 차트 (Recharts)

### Phase 8: Advanced Documents -- NOT STARTED
- [ ] 이미지 OCR
- [ ] 오디오 → 텍스트 (whisper)
- [ ] 비디오 → 오디오 → 텍스트
- [ ] XLSX, PPTX 추출기

### Phase 9: Scale & Polish -- NOT STARTED
- [ ] 카테고리별 DB 샤딩
- [ ] FTS5 trigram 토크나이저 (CJK)
- [ ] 벤치마크 (10만+ 파일)
- [ ] Docker 이미지
- [ ] pip 패키지 배포

### Phase 10: Permission & Multi-tenancy -- NOT STARTED

현재 구현: Ask 탭에서 `mode: "read" | "write"` 클라이언트 토글로 tool 노출 제어.
write tool 실행 전 사용자 수동 승인(pending_action 카드) 필수.

로드맵:

- [ ] **API 키 기반 권한** — 읽기 전용 키 / 쓰기 키 분리 발급
  - `/api/ask` 헤더 `X-API-Key` 검증
  - 키 없으면 read-only 강제
- [ ] **RBAC (Role-Based Access Control)**
  - Admin: 모든 tool + 카테고리 관리 + 사용자 관리
  - Editor: KB 읽기/쓰기, 승인 없이 저장 가능
  - Viewer: 읽기 전용 (search_knowledge, get_document 만)
- [ ] **로그인 시스템** — JWT or session 기반, 역할 저장
- [ ] **감사 로그** — write tool 실행 기록 (누가, 언제, 무엇을)
- [ ] **Enterprise 모드** — 환경변수 `MODE=enterprise` 시 write tool 완전 비활성화
  - 별도 관리자 대시보드에서만 KB 편집 가능
- [ ] **개인 모드 자동화** — `MODE=personal` 시 write 승인 없이 자동 저장 옵션

## MVP (달성)

Phase 0~1 완료로 MVP 달성:
- 17개 MCP 도구 등록, 어떤 LLM이든 연결 가능
- 계층적 BM25 검색 (임베딩 없이)
- 자동 카테고리 분류, 충돌 감지, 리콜 추적
- LLM이 DDL 자유롭게 생성/진화
- Web UI (3D 그래프 + 검색 + 타임라인 + 통계)
- Claude Sonnet으로 실제 E2E 검증 완료
