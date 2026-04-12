# Testing

## 테스트 종류

| 테스트 | 파일 | LLM 키 필요 | 서버 필요 | 결과 |
|--------|------|------------|----------|------|
| MCP 도구 E2E | test_e2e.py | 아니오 | 아니오 | 58/58 pass |
| Claude API E2E | test_llm_e2e.py | 예 (Anthropic) | 아니오 | 14/14 pass |
| Claude 대화 로깅 | test_llm_verbose.py | 예 | 아니오 | 6/6 시나리오 |
| 프론트엔드 E2E | test_frontend.py | 아니오 | 예 (7777) | 렌더링 확인 |

## 1. MCP 도구 E2E (test_e2e.py)

LLM 없이 MCP 도구 함수를 직접 호출하여 전체 시나리오를 검증.
임시 디렉토리에서 실행되므로 기존 데이터에 영향 없음.

```bash
PYTHONPATH=/home/superpikachu/src python3 tests/test_e2e.py
```

### 13개 Phase, 58개 assertion

| Phase | 내용 | 검증 항목 |
|-------|------|----------|
| 1 | 대화에서 학습 | learn_fact 4건, 파일 생성, 경로 정확성 |
| 2 | 지식 검색 | BM25 매칭, 점수, 미존재 쿼리 빈 결과 |
| 3 | 파일 읽기 | 내용 반환, frontmatter 포함, 파일 크기 |
| 4 | 구조 조회 | 카테고리 트리, 폴더 존재 확인 |
| 5 | DB 테이블 생성 | CREATE TABLE, INSERT, DDL 이력 기록 |
| 6 | DB 쿼리 | SELECT 결과, 스키마 조회, 컬럼 수 |
| 7 | 시스템 테이블 보호 | DROP/DELETE/ALTER 차단 확인 |
| 8 | 충돌 감지 | 중복 학습 시 append, 충돌 후보 |
| 9 | 상태/건강체크 | 파일수/카테고리/리콜/DB테이블/lint |
| 10 | 지식 관리 | update, archive, reorganize(create_category) |
| 11 | 스키마 진화 | ALTER TABLE, 새 테이블, 사용자 테이블 목록 |
| 12 | 리콜 추적 | 검색 횟수 축적, recall_count 반영 |
| 13 | 그래프 데이터 | nodes/clusters 존재, recalls > 0, category 설정 |

## 2. Claude API E2E (test_llm_e2e.py)

실제 Claude (claude-sonnet-4-20250514) 가 MCP 도구를 호출하는 전체 흐름 검증.
Anthropic API 키 필요.

```bash
ANTHROPIC_API_KEY=sk-ant-... PYTHONPATH=/home/superpikachu/src python3 tests/test_llm_e2e.py
```

### 7개 시나리오, 14개 assertion

| 시나리오 | 프롬프트 | Claude의 행동 | 검증 |
|---------|---------|-------------|------|
| 1 | "walrus operator 저장해줘" | learn_fact 호출, programming 분류 | 도구 호출 + 카테고리 |
| 2 | "Python 뭐 있어?" | knowledge_search 호출 | 검색 실행 확인 |
| 3 | "3가지 사실 저장" | learn_fact 3회 병렬 호출 | 다중 호출 + 다른 카테고리 |
| 4 | "bookmarks 테이블 만들어" | db_execute CREATE + INSERT | 테이블 생성 + 데이터 삽입 |
| 5 | "북마크 뭐 있어?" | db_query SELECT | 쿼리 실행 + GitHub 언급 |
| 6 | "walrus 검색해서 전체 보여줘" | search → get 2단계 | 검색 + 파일 읽기 |

### 실제 발견된 LLM 행동 특성

1. **카테고리 자동 분류**: 사용자가 지정하면 따르고, 안 하면 내용 기반 추론
2. **병렬 호출**: 독립적인 learn_fact 3개를 한 번에 동시 호출
3. **에러 복구**: db_execute params 바인딩 실패 → SQL 직접 삽입으로 자가 수정
4. **2단계 워크플로우**: knowledge_search → knowledge_get 연쇄 호출
5. **내용 보충**: 사용자가 안 말한 추가 용례까지 보충하여 저장

## 3. Claude 대화 전문 (test_llm_verbose.py)

test_llm_e2e.py와 같은 시나리오지만 전체 대화 내용을 출력.
프롬프트, Claude 응답, 도구 호출 입력, 도구 결과를 모두 기록.

```bash
ANTHROPIC_API_KEY=sk-ant-... PYTHONPATH=/home/superpikachu/src python3 tests/test_llm_verbose.py
```

출력 예시:
```
>> USER:
I just learned that Python's walrus operator...

<< CLAUDE calls learn_fact:
   input: {"category": "programming", "title": "Python Walrus Operator...

   >> TOOL RESULT (learn_fact):
   {"path": "programming/python-walrus-operator---assignment-expressions.md", "created": true}

<< CLAUDE:
I've saved the Python walrus operator fact...
```

## 4. Playwright 반복 테스트 유틸 (tests/pw.py)

반복적인 UI 디버깅/회귀 테스트용 헬퍼 모음. 컨텍스트를 많이 차지하지 않도록 자주 쓰는 코드를 미리 정의해 둠.

### 전체 스위트 실행

```bash
python3 tests/pw.py               # 스크린샷 /tmp/pw_*.png
python3 tests/pw.py /tmp/my_run   # 경로 지정
```

### 헬퍼 함수

```python
from tests.pw import snap, graph_state, close_sidepanel, switch_mode, switch_tab
from tests.pw import run_graph_suite, run_mobile_suite, URL, SETTLE

# 스크린샷 + 캔버스 zoom/util 출력
s = snap(page, "label", "/tmp/out.png")
# → {"k": "1.25", "ux": "60%", "uy": "80%", ...}

# 스크린샷 없이 상태만
s = graph_state(page)

# 에러 수집
errs = []; page_errors(page, errs)

# UI 조작
close_sidepanel(page)
switch_mode(page, "Galaxy")        # Constellation / Galaxy
switch_tab(page,  "DB")            # Graph / Structure / DB / Timeline / Stats
```

### 표준 시나리오 (run_graph_suite)

| # | 동작 | 확인 포인트 |
|---|------|------------|
| 01 | 초기 로드 | zoom>0, util>5% |
| 02 | 스크롤 줌인 | zoom 증가 |
| 03 | 스크롤 줌아웃 | zoom 감소 |
| 04 | 노드 클릭 | SidePanel, 그래프 유지 |
| 05 | 드래그 | 그래프 유지 |
| 06 | 드래그 후 스크롤 | **사라지면 버그** |
| 07 | Galaxy 전환 | 원형 배치 |
| 08 | Constellation 복귀 | 정상 표시 |

### 인라인 사용 예시

```python
from playwright.sync_api import sync_playwright
from tests.pw import snap, URL, SETTLE
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(URL, wait_until="networkidle")
    time.sleep(SETTLE)
    snap(page, "initial", "/tmp/t01.png")
    browser.close()
```

### 주요 버그 히스토리

| 증상 | 원인 | 수정 |
|------|------|------|
| 드래그 후 스크롤하면 사라짐 | `useEffect`에 의존성 없어 매 렌더마다 force reheat | `useLayoutEffect` + mount-once |
| zoomToFit 작동 안 함 | tooltip 내부 에러, 타이밍 문제 | `onEngineStop` 콜백에서 호출 |
| 노드 전부 한 점에 뭉침 | DB 노드 고립으로 force layout 망가짐 | 고립 DB 노드에 `fx/fy` 핀 고정 |
| PAGE ERROR: node not found | DB 엣지가 없는 wiki 파일 참조 | `wiki_path_set`으로 엣지 필터링 |
| Galaxy→Constellation 빈 화면 | custom force 함수 타입 오류 | 단순 d3Force 호출로 교체 |

---

## 5. 프론트엔드 E2E (test_frontend.py)

Playwright headless Chromium으로 실제 브라우저 렌더링 검증.
서버가 7777 포트에서 실행 중이어야 함.

```bash
# 서버 실행 확인
pm2 status superpikachu-web

# 테스트 실행
python3 tests/test_frontend.py
```

### 검증 항목
- React 앱 마운트 (root innerHTML > 100)
- Constellation/Galaxy/Heatmap/Structure 버튼 존재
- FILES/CATEGORIES/RECALLS/CONFLICTS KPI 표시
- 검색 입력 존재 및 결과 표시
- Timeline 탭 렌더링 (learn 이벤트)
- Stats 탭 렌더링 (파일수, 테이블 목록)
- 3D 캔버스 렌더링 (WebGL)

### 스크린샷
`tests/screenshots/` 에 PNG 캡처:
- 01_graph.png: 초기 그래프 뷰
- 02_galaxy.png: Galaxy 모드
- 03_search.png: 검색 결과
- 04_timeline.png: 타임라인 탭
- 05_stats.png: 통계 탭

### headless 환경 제약
- WebGL 소프트웨어 래스터라이저 사용 (--disable-gpu)
- 캔버스 캡처가 불완전할 수 있음 (Three.js 렌더링 제한)
- 텍스트 기반 검증이 더 안정적 (`document.body.innerText` 활용)

## API 통합 테스트 결과

FastAPI TestClient로 모든 엔드포인트 검증 (test_e2e.py와 별도로 seed.py 데이터 기반):

| 엔드포인트 | 결과 |
|-----------|------|
| GET /api/graph | 21 nodes, 40 edges, 5 clusters |
| GET /api/search?q=python | 7 results |
| GET /api/knowledge/programming/python-basics.md | 802 chars |
| GET /api/tree | 21 files |
| GET /api/stats | 21 files, 112 recalls, 1 conflict |
| GET /api/timeline | 21 events |
| GET /api/conflicts | 1 pending |
| GET /api/db/tables | 14 tables (12 system + 2 user) |
| POST /api/db/query | projects 3행, reading_list 3행 |
| GET / | HTML 200, JS bundle 1.6MB |
