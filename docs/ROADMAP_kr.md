# 로드맵

English: [ROADMAP.md](ROADMAP.md)

ohkb 버전은 **0.1.0**부터 시작합니다.

**포지션:** 에이전트를 위한 간단한 로컬 지식 베이스.
ohkb는 모델을 호출하지 않습니다. 파일이 진실이고, FTS5는 재구축 가능한 인덱스입니다.

---

## 0.2.0 — 검색 토큰 (현재)

| 영역 | 내용 |
|------|------|
| 검색 | 한글·가나·한자 두 글자 bigram + 나머지 단어 통째로, OR 질의 + BM25 가중치 (AND·접두어·대체 결과 5개 제한 없음) |
| 색인 | 검색 토큰 열(스키마 2), 0.1.0 DB는 처음 열 때 자동 이전, 수정 후 이전 색인 행이 남지 않음 |

## 0.1.0 — 코어

| 영역 | 내용 |
|------|------|
| CLI | learn, search, get, edit, meta, forget, restore, tree, status, lint, reindex, index, serve |
| 라이프사이클 | init, source add/list, log, extract, related |
| 검색 | FTS5 BM25, 카테고리 prefix, limit |
| 정합성 | dual-write, 경로 재배치, 아카이브 버전, reindex, lint drift |
| MCP | readonly / managed / autonomous |
| 계약 | 임베딩 없음, 모델 호출 없음, 로컬 우선 |

### 의도적 제외

- 구조화 `ohkb db` 다중 테이블
- 무거운 컴파일 파이프라인
- 자동 병합/분할/오래됨 에이전트
- 웹 UI를 주 제품면으로 취급

---

## 백로그

1. **`ohkb db`** — 에이전트 소유 SQLite 테이블
2. **지식 위생 시그널** — 유사 항목, stale, related 고도화 (모델 호출 없음)
3. **사람용 인터페이스 컨셉** — 현재는 문서만 존재하며 Web/HTTP 런타임은 제공하지 않음. 구현하려면 별도 제품·보안 결정 필요 ([WEB_UI_kr.md](WEB_UI_kr.md))

---

## 버전 정책

| 라인 | 의미 |
|------|------|
| **0.1.x** | 코어 KB + MCP + 라이프사이클 헬퍼 |
| **0.2.x** | 검색 토큰 (스키마 2) |
| **0.3.x** | 첫 대형 추가 기능 (유력: `db`) |
| **1.0** | 안정 CLI/MCP 계약 |

`pyproject.toml`과 `ohkb.__version__`을 동일하게 유지합니다.
