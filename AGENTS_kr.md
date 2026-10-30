# ohkb — 코딩 에이전트 개발 가이드

English: [AGENTS.md](AGENTS.md)

> **ohkb** — 에이전트를 위한 간단한 로컬 지식 베이스.
> 임베딩 없음. 벡터 DB 없음. **ohkb는 모델을 호출하지 않음.**
> Markdown + SQLite FTS5. 버전 **0.2.0**.

이 파일은 **이 저장소에서 작업하는 에이전트**를 위한 소스 오브 트루스입니다.

---

## 제품 위치

| ohkb가 하는 일 | ohkb가 아닌 것 |
|----------------|----------------|
| 에이전트용 기억 **도구** (CLI + MCP) | 임베딩/벡터 RAG 스택 |
| 어떤 모델·에이전트 호스트든 | 특정 IDE/채팅 제품 종속 |
| FS + FTS dual-write 기판 | LLM을 호출하는 시스템 |
| 원자 사실 + tags/aliases | 범용 노트 앱 |

**한 줄:** 에이전트가 *기억*할 때 쓰는 도구 — 위키를 대신 써 주는 모델이 아님.

**원칙:** `wiki/` 파일이 진실. SQLite는 `ohkb reindex`로 재구축 가능한 인덱스.

---

## 스택 & 레이아웃

Python 3.10+, Click, FTS5, optional MCP (`ohkb[serve]`), hatchling, ruff, pytest.

```
src/ohkb/  cli.py serve.py kb.py wiki.py store.py models.py config.py index.py
           sources/log/extract helpers live under wiki/config/kb
tests/     test_kb.py test_basic.py test_index.py test_serve.py …
```

## 빌드 / 테스트 / 린트

```bash
uv sync --extra dev
uv run ohkb --version
pytest
ruff check src/ tests/
```

테스트: `OHKB_DIR` + real FS/SQLite. 모킹 금지.

## 아키텍처

Presentation → `kb.py` → wiki + store → models + config.
레이어 건너뛰지 말 것. 뮤테이션 = FS 먼저 → FTS → (선택) `_index.md` 갱신.

## CLI / MCP

영어 [AGENTS.md](AGENTS.md)의 표와 동일.
모드: readonly / managed / autonomous.

## 불변조건

- 제목/카테고리 변경 → 파일 재배치, orphan 금지
- rename 충돌 → FileExistsError
- edit는 frontmatter 금지 → meta
- re-forget → 타임스탬프 버전 아카이브
- in_sync false → reindex

## 코드 스타일

`from __future__ import annotations`, isort 순서, `str | None`, 커스텀 예외 금지,
서비스는 raise / CLI는 SystemExit(1) / MCP는 전파.

## 하지 말 것

- ohkb 안에서 모델 호출
- 요청 없이 로드맵 기능 확장
- dual-write 깨기

자세한 백로그: [docs/ROADMAP_kr.md](docs/ROADMAP_kr.md)
