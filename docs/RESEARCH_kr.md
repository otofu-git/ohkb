# Research Summary

English: [RESEARCH.md](RESEARCH.md)

ohkb 설계에 영향을 준 기존 프로젝트와 아이디어 조사 결과.

## 1. 기존 RAG/메모리 프로젝트 분석

### Tier 1: 대형 프로젝트

| 프로젝트 | Stars | 핵심 | 자동학습 | 임베딩 | ohkb와의 차이 |
|---------|-------|------|---------|--------|-------------|
| Dify | 136k | 올인원 AI 플랫폼 | X | 필수 | 자동학습/자동정리 없음, 수동 업로드만 |
| LangChain | 132k | 에이전트 프레임워크 | X | 필수 | 도구킷일 뿐, 지식 관리 아님 |
| RAGFlow | 77k | 문서 이해 RAG | X | 필수 | 임베딩 의존, 자동학습 없음 |
| Mem0 | 51.9k | AI 메모리 레이어 | △ | 내부 | 클라우드 API, 블랙박스 |
| OpenClaw | 348k | 개인 AI 비서 | O | 필수 | 개인비서 전용, flat 구조, 범용 아님 |
| CrewAI | 48k | 에이전트 메모리 | O | 내부 | 에이전트 프레임워크 종속 |
| Khoj | 33.9k | 개인 지식 검색 | X | 필수 | 노트 앱 통합형, 임베딩 의존 |
| LightRAG | 32k | KG + RAG | X | 필수 | 그래프 기반이지만 임베딩 필수 |
| MS GraphRAG | 32k | 그래프 RAG | X | 필수 | 인덱싱 비용 매우 높음 |
| Supermemory | 21k | 메모리 엔진 | O | 내부 | 클라우드 API, 유료, 블랙박스 |

### 핵심 발견

- **모든 대형 프로젝트가 임베딩/벡터 DB에 의존**
- 자동학습은 OpenClaw, CrewAI, Supermemory만
- **"임베딩 없이 구조화된 MD 기반 범용 RAG"는 빈 시장**

## 2. OpenClaw 메모리 심층 분석 (코드 레벨)

### 아키텍처

- memory-core 플러그인 (`extensions/memory-core/`)
- MEMORY.md (장기) + memory/YYYY-MM-DD.md (일별)
- SQLite + FTS5 + sqlite-vec 하이브리드 검색
- Dreaming 시스템 (cron 기반 자동 승격)

### Dreaming 알고리즘 (코드에서 확인)

6가지 가중 신호 (문서는 4개라고 하지만 코드는 6개):

```
frequency:     0.24  log1p(recallCount) / log1p(10)
relevance:     0.30  totalScore / recallCount
diversity:     0.15  uniqueQueries / 5
recency:       0.15  e^(-ln2/14 * ageDays)
consolidation: 0.10  여러 날에 걸쳐 리콜 (spaced repetition)
conceptual:    0.06  컨셉 태그 다양성
```

게이트: minScore(0.75) AND minRecallCount(3) AND minUniqueQueries(2)
모드: core(매일3AM), rem(6시간), deep(12시간)

### 하이브리드 검색

```
score = 0.7 * vectorScore + 0.3 * BM25Score
```

- 선택적 temporal decay (30일 반감기)
- 선택적 MMR 다양성 (Jaccard, λ=0.7)
- MEMORY.md는 시간 감쇠 면제 (evergreen)

### OpenClaw에 없는 것 (ohkb의 기회)

1. 자동 카테고리 분류 (flat MEMORY.md만)
2. 충돌 감지/병합 (append만)
3. 범용성 (개인 비서 전용)
4. 임베딩 없는 운영 (sqlite-vec 필수)

## 3. 자율 에이전트 프레임워크 분석

### CrewAI Memory (가장 진보적)

- LLM이 계층 스코프를 자동 추론 (예: `/project/alpha/architecture`)
- 자동 병합/중복제거 (consolidation)
- composite scoring (semantic + recency + importance)
- LanceDB 저장, TUI 브라우저
- **가장 성숙한 자동 분류 시스템**

### BabyAGI (가장 급진적)

- 지식을 "함수"로 저장 (실행 가능한 코드)
- 스스로 새 함수 생성 (self_build)
- 실험적, 프로덕션 아님
- **유일하게 자율 확장을 시도하는 프로젝트**

### Devin (가장 세련된 UX)

- Knowledge 시스템: 팁/지침/컨텍스트 저장
- 자동 분류 (auto-organize 기능)
- LLM이 지식 업데이트 제안
- 비공개, 상용

## 4. Karpathy LLM Wiki (2026-04-04)

### 핵심 아이디어

> "RAG처럼 매번 처음부터 재발견하는 대신, LLM이 점진적으로 위키를 쌓고 관리한다."

### 3계층 구조

1. **Raw Sources** - 불변 원본 (소스 오브 트루스)
2. **Wiki** - LLM이 작성/관리하는 MD 파일들
3. **Schema** - LLM에게 위키 규칙을 알려주는 설정 문서

### 핵심 연산

- **Ingest**: 소스 → LLM이 읽고 → 위키에 통합 (10~15 페이지 터치)
- **Query**: 위키 검색 → 답변 생성 → 좋은 답변은 위키에 재투입
- **Lint**: 건강 체크 (모순, 고아, stale, 빈 곳)

### 인덱싱

- **index.md**: 전체 위키 카탈로그. 검색 진입점. ohkb의 `_index.md`와 동일한 역할.
- ~100 소스 규모에서는 index.md만으로 충분 (임베딩 불필요)

### 하루만에 3,168 stars → 수요 증명

## 5. 댓글에서의 프로덕션 인사이트

### bluewater8008 (프로덕션 경험)

1. **타입별 분류 후 추출**: 문서를 일괄 처리하지 말고 타입(보고서/편지/대화록 등)별로 분류 후 다른 전략
2. **토큰 예산**: L0(200) → L1(1-2K) → L2(2-5K) → L3(5-20K) 4단계
3. **엔티티 타입별 템플릿**: person/event/document 등 타입별 필수 섹션 → ohkb의 `entity_type` 필드로 반영
4. **모든 작업 → 두 가지 결과물**: 답변 + 위키 업데이트
5. **크로스 도메인 설계**: 처음부터 도메인 태그를 frontmatter에
6. **검증은 사람이**: 소스 인용 규칙, 정기 감수

### mpazik (Binder 개발자)

> "파일이 서서히 DB가 되는 것 대신, 구조화 데이터에서 시작해서 MD로 렌더링하라. 인덱스는 쿼리여야 한다."

SQLite 트랜잭션 로그 + MD 양방향 편집 아키텍처.
→ ohkb의 "SQLite = 색인, MD = 본체" 설계와 일치.

### karesansui-u (delta-zero)

> "토큰 양이 아니라 모순의 축적이 성능 저하의 근본 원인. Lean 증명 완료."

→ 원자적 파일 구조 (하나의 사실 = 하나의 파일)의 이론적 근거.

### sage-wiki (Go 구현체)

- `sage-wiki init` (기존 마크다운 디렉터리에서)
- `sage-wiki compile` / `compile --watch`
- `sage-wiki search` / `query`
- `sage-wiki serve` (MCP 서버)
- 단일 Go 바이너리. 가장 완성도 높은 Karpathy 구현체.
- 하지만 자동 분류/Python 패키지/pip 설치 없음.

## 6. 현존 시스템 능력 비교

현재 ohkb가 달성한 범위:

| | 자동학습 | 카테고리분류 | 투명MD | BM25검색 | MCP서버 |
|---|---|---|---|---|---|
| OpenClaw | O | X | O | O (하이브리드) | X |
| CrewAI | O | O | O | X (임베딩) | X |
| Supermemory | O | O | X | X (임베딩) | X |
| sage-wiki | X | X | O | O | O |
| **ohkb** | **O** | **O** | **O** | **O** | **O** |

## 7. 검색 키워드 (0 결과들)

GitHub에서 다음 키워드로 검색하여 모두 0 결과 확인 (조사 당시):

- `hierarchical knowledge base LLM routing`
- `structured context injection LLM markdown`
- `agentic RAG file system routing knowledge`
- `cursor rules knowledge context LLM`
- `wiki RAG LLM folder structure`
- `prompt knowledge management system LLM context`

→ **이 개념의 범용 프레임워크가 존재하지 않음을 재확인**
