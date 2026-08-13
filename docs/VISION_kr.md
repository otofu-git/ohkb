# ohkb - Vision & Philosophy

English: [VISION.md](VISION.md)

## One-Line Definition

**ohkb** — 에이전트를 위한 간단한 로컬 지식 베이스.
어떤 LLM 에이전트든 CLI/MCP로 붙일 수 있는 로컬 지식 백엔드.
텍스트는 MD, 색인은 SQLite FTS5, 임베딩 없음, 모델 호출 없음, 완전 오픈소스.

## Problem Statement

### 기존 RAG의 문제

- 임베딩 모델이 붙으면 느리고 비싸다
- 벡터 DB 인프라 운영 비용과 복잡성
- 지식이 숫자(벡터)로 변환되면 사람이 읽을 수 없다 (블랙박스)
- 매 질문마다 지식을 처음부터 재발견한다 (축적이 없음)
- 시맨틱 미스매치: 임베딩이 항상 의미적으로 정확한 매칭을 보장하지 않음

### 기존 메모리 시스템의 한계

- **OpenClaw**: MEMORY.md 하나에 flat하게 append만. 카테고리/충돌해결 없음
- **Supermemory/Mem0**: 클라우드 API 의존, 블랙박스, 유료
- **CrewAI Memory**: 에이전트 프레임워크에 종속, 범용 아님
- **Claude Code auto memory**: 코딩 에이전트 전용, 범용 아님

### 핵심 관찰

- CLAUDE.md, .cursor/rules/, OpenCode skills 같은 패턴이 이미 실전에서 작동하고 있음
- Karpathy의 LLM Wiki (2026-04-04) 패턴이 하루만에 3,168 stars → 수요 증명
- 하지만 "계층적 MD 구조 + BM25 키워드 검색"을 범용 프레임워크로 만든 프로젝트는 현재 존재하지 않음
- "너무 단순해서 프레임워크화할 동기가 없었던" 빈 시장

## Core Philosophy

### 6대 원칙

1. **시스템은 LLM을 절대 호출하지 않는다**
   - LLM이 도구를 호출하고, 결과를 받아서 판단
   - 시스템은 순수 데이터 처리만 담당
   - 이로써 어떤 LLM이든 (Claude, GPT, Llama, Gemini...) 연결 가능

2. **텍스트 지식 = MD 파일**
   - 사람이 직접 읽고 편집 가능
   - git으로 버전 관리 가능
   - 평문이라 어떤 에디터·도구로든 열 수 있음
   - 지식은 영구적이고 복리로 쌓이는 산출물

3. **색인 = SQLite FTS5 (고정 스키마)**
   - 날짜, 태그, 카테고리 등 색인이 필요한 데이터만 SQLite
   - BM25 랭킹: title(10×) > tags(5×) > aliases(3×) > content(1×)
   - LLM이 저장 시점에 태그와 별칭을 직접 결정 → 임베딩 없이 의미 기반 검색 가능
   - mpazik(Binder): "인덱스는 에이전트가 수동 관리하는 파일이 아니라 쿼리여야 한다"

4. **임베딩 없음, 벡터 DB 없음**
   - BM25 + 태그/별칭으로 충분
   - 비용 0, 인프라 0, 완전 로컬
   - SQLite FTS5가 수백만 행도 밀리초 검색

5. **지식은 복리로 쌓인다**
   - 질문의 답변도 위키에 재투입 (compounding)
   - bluewater: "모든 작업은 두 가지 결과물을 만든다 (답변 + 위키 업데이트)"
   - 원자적 파일 구조 (하나의 사실 = 하나의 파일)로 정밀한 업데이트 가능

6. **완전 오픈소스, 완전 로컬**
   - 외부 서비스 의존 없음 (LLM API 제외)
   - 데이터가 사용자 머신에만 존재
   - 어떤 환경에서든 실행 가능

## What Makes This Different

### vs Karpathy LLM Wiki

| | Karpathy LLM Wiki | ohkb |
|---|---|---|
| 형태 | 패턴/아이디어 문서 | MCP 서버 도구 (범용 인프라) |
| LLM 관계 | 특정 에이전트에 문서를 붙여서 사용 | 어떤 LLM이든 MCP로 연결 |
| 검색 | qmd (외부 도구) | 내장 SQLite FTS5 BM25 |
| 편집 | 수동 / 에이전트 자유 편집 | `learn`, `edit`, `meta`, `forget` 등 고정 도구 계약 |
| 분류 | 스키마에 의존 | 카테고리 + 중첩 경로 지원 |
| 인터페이스 | 에이전트 + 로컬 파일 | CLI + MCP 서버 |

### vs Supermemory

| | Supermemory | ohkb |
|---|---|---|
| 저장소 | 클라우드 API | 로컬 MD + SQLite |
| 임베딩 | 필수 (벡터 검색) | 없음 (BM25 + 태그) |
| 비용 | 유료 API | 완전 무료 |
| 투명성 | API 뒤 블랙박스 | 사람이 직접 읽기/편집 |
| 오프라인 | 불가 | 가능 (완전 로컬) |
| git 추적 | 불가 | 가능 (MD 파일) |

### vs OpenClaw Memory

| | OpenClaw | ohkb |
|---|---|---|
| 구조 | MEMORY.md 하나에 flat append | 계층적 폴더/파일 구조 |
| 검색 | 임베딩 + BM25 하이브리드 | 임베딩 없이 BM25 |
| 분류 | 없음 (일별 노트만) | 카테고리 자동 생성/관리 |
| 범용성 | 개인 비서 전용 | 어떤 LLM/도메인이든 |

## Target Users

### Primary: 소규모 팀 / 1인 개발자

- 벡터 DB 세팅하기 귀찮고, Dify/RAGFlow는 과하고, 비용도 부담
- "쉽고 싸게 우리 문서 기반으로 AI에게 질문하기" 수요

### Secondary: AI 에이전트 빌더

- 자기 에이전트에 장기 메모리/지식 시스템을 붙이고 싶은 개발자
- MCP 도구로 바로 연결하여 사용

### Tertiary: 지식 노동자 (연구자, 학생, 작가 등)

- 에이전트와 함께 지식을 쌓고 싶지만 벡터 인프라 없이 쓰고 싶은 사람

## Inspiration & References

- **Karpathy LLM Wiki** (2026-04-04): 핵심 패턴 원본. "LLM이 위키를 쓰고 관리한다"
- **mpazik/Binder**: "구조화 데이터 → MD 렌더링" 방향. SQLite + 트랜잭션 로그
- **bluewater8008**: 프로덕션 교훈. 타입별 분류, 토큰 예산, 엔티티 템플릿
- **karesansui-u/delta-zero**: "모순 축적이 성능 저하의 근본 원인" 수학적 증명
- **Vannevar Bush Memex (1945)**: "개인 큐레이션 지식 저장소 + 연관 트레일"
- **sage-wiki**: Go 구현의 Karpathy 패턴. 단일 바이너리, MCP 서버 포함
