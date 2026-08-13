# MCP Tools Reference

English: [MCP_TOOLS.md](MCP_TOOLS.md)

ohkb MCP 서버(`ohkb serve`)가 노출하는 툴, 리소스, 프롬프트의 전체 사양.
구현 파일: `src/ohkb/serve.py`

## 서버 모드

```
ohkb serve                    # autonomous (기본)
ohkb serve --mode readonly    # 읽기 전용
ohkb serve --mode managed     # 확인 유도 쓰기
ohkb serve --mode autonomous  # 즉시 쓰기
```

| 모드 | 읽기 툴 | 쓰기 툴 |
|------|--------|--------|
| `readonly` | O | X |
| `managed` | O | O (LLM 지침에 확인 유도) |
| `autonomous` | O | O (즉시 실행) |

## Resources

### `ohkb://index`

**설명**: KB 전체 구조 요약. 에이전트가 가장 먼저 읽어야 할 리소스.

카테고리별 엔트리 목록, 태그, 파일 크기, 타임스탬프가 포함된 Markdown을 반환한다.
이 리소스는 모든 쓰기 작업 후 자동으로 갱신된다.

**반환**: Markdown 문자열 (`_index.md` 내용)

---

## Read Tools (전 모드 사용 가능)

### `search`

전문 검색 (FTS5 BM25 랭킹).

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `query` | string | O | 검색 키워드 (자동 escape, FTS5 특수문자 안전) |
| `category` | string | - | 카테고리 prefix 필터. `"python"`은 `"python/internals"`도 포함 |
| `limit` | integer | - | 최대 결과 수 (기본 20) |

**반환**: JSON 배열

```json
[
  {
    "path": "python/free-threaded-python.md",
    "title": "자유 스레드 Python",
    "category": "python",
    "tags": "GIL,CPython,free-threading",
    "aliases": "nogil,no-GIL Python",
    "entity_type": "concept",
    "score": 1.0
  }
]
```

`score`는 결과 집합 내 상대 점수 (최고 매치 = 1.0).

결과 없을 때: `"No results found."` 문자열 반환

**BM25 가중치**: title(10×) > tags(5×) > aliases(3×) > content(1×)

---

### `get`

줄 번호와 함께 엔트리 전체 내용 읽기.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | O | `"category/file.md"` 형식의 상대 경로 |

**반환**: 포맷된 텍스트

```
=== python/free-threaded-python.md (847 chars, 21 lines) ===
   1: ---
   2: title: 자유 스레드 Python
   ...
  21: Python 3.14에서 안정화됨.
```

파일 없을 때: `FileNotFoundError` 발생 (MCP SDK가 `isError=True`로 처리)

---

### `tree`

KB 구조 탐색.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | - | 줌인할 카테고리 경로 (기본: 루트) |
| `depth` | integer | - | 확장 깊이 (기본 2) |

**반환**: JSON

```json
{
  "path": "/",
  "depth": 2,
  "tree": {
    "python": {
      "free-threaded-python.md": null,
      "internals": {"_truncated": true}
    },
    "rust": {
      "ownership.md": null
    }
  }
}
```

`null` = 파일, `{"_truncated": true}` = depth 제한으로 잘린 디렉토리.
잘린 디렉토리는 `tree(path="python/internals", depth=2)`로 다시 호출.

---

### `status`

KB 통계.

파라미터 없음.

**반환**: JSON

```json
{
  "indexed_entries": 42,
  "files_on_disk": 42,
  "categories": ["python", "python/internals", "rust"],
  "data_dir": "/Users/user/.ohkb",
  "in_sync": true
}
```

`in_sync`가 `false`이면 `reindex` 실행.

---

### `lint`

KB 건강 체크.

파라미터 없음.

**반환**: 이슈 없으면 `"No issues found."`, 있으면 JSON 배열

```json
[
  {
    "path": "python/big-file.md",
    "level": "warning",
    "issue": "oversized",
    "detail": "File is 4521 chars (recommended max: 3000)"
  },
  {
    "path": "rust/ownership.md",
    "level": "warning",
    "issue": "missing_tags",
    "detail": "No tags defined. Search quality will be poor."
  }
]
```

**검사 항목**:
- `unindexed` / `missing_file`: 디스크 ↔ 인덱스 drift (`reindex`로 복구)
- `oversized`: 3000자 초과 파일
- `missing_tags` / `missing_aliases`: 태그/별칭 없음
- `invalid_frontmatter`: YAML 파싱 실패
- `category_mismatch`: frontmatter category ≠ 경로
- `slug_mismatch`: 파일명 ≠ 제목 슬러그
- `empty_category`: MD 파일 없는 빈 카테고리 디렉토리

---

### `reindex`

디스크의 wiki 파일을 기준으로 FTS5 인덱스를 재구축한다 (파일이 진실).

파라미터 없음.

**반환**: JSON

```json
{"indexed": 42, "errors": [], "status": "ok"}
```

---

## Write Tools (managed / autonomous 모드)

### `learn`

새 지식 엔트리 저장.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `content` | string | O | 엔트리 본문 (< 3000자 권장) |
| `title` | string | O | 엔트리 제목 |
| `category` | string | O | 카테고리 경로 (`"python"` 또는 `"python/internals"`) |
| `tags` | string | - | 쉼표 구분 태그 (3-7개 권장) |
| `aliases` | string | - | 쉼표 구분 별칭/동의어 |
| `entity_type` | string | - | `concept`(기본) / `person` / `event` / `project` / `reference` |
| `source` | string | - | `manual`(기본) / `document` / `reference` |
| `overwrite` | boolean | - | 기존 파일 덮어쓰기 (기본: false) |

**반환**: JSON

```json
{
  "path": "python/free-threaded-python.md",
  "status": "created",
  "chars": 243,
  "warnings": ["No tags provided. Search quality depends on good tags."]
}
```

`FileExistsError`: 이미 존재하고 `overwrite=false`일 때
`ValueError`: content가 비어있을 때

**워크플로우**: 저장 전 `search`로 중복 확인 필수.

---

### `edit`

줄 레벨 편집. 정확히 한 가지 편집 연산만 지정해야 한다.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | O | `"category/file.md"` |
| `content` | string | - | 새 내용 (replace/insert 연산에 필요) |
| `line` | integer | - | 이 줄 번호를 교체 (1-indexed) |
| `line_start` | integer | - | 범위 교체 시작 줄 (`line_end`와 함께) |
| `line_end` | integer | - | 범위 교체 끝 줄 (`line_start`와 함께) |
| `after` | integer | - | 이 줄 번호 뒤에 삽입 |
| `delete` | integer | - | 이 줄 번호 삭제 |

**반환**: JSON

```json
{
  "path": "python/free-threaded-python.md",
  "action": "replaced line 11",
  "chars": 251,
  "lines": 21
}
```

**워크플로우**: `get`으로 줄 번호 확인 후 편집.

frontmatter 라인은 편집할 수 없다. 메타데이터는 `meta`를 사용한다.

---

### `meta`

frontmatter 메타데이터 업데이트. 본문은 변경되지 않는다.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | O | `"category/file.md"` |
| `add_tags` | string | - | 쉼표 구분, 추가할 태그 |
| `remove_tags` | string | - | 쉼표 구분, 제거할 태그 |
| `add_aliases` | string | - | 쉼표 구분, 추가할 별칭 |
| `remove_aliases` | string | - | 쉼표 구분, 제거할 별칭 |
| `title` | string | - | 새 제목 (빈 문자열 = 변경 없음) |
| `category` | string | - | 새 카테고리 (파일 이동 발생, 빈 문자열 = 변경 없음) |
| `entity_type` | string | - | 새 entity type (빈 문자열 = 변경 없음) |

**반환**: JSON

```json
{"path": "python/free-threaded-python.md", "status": "updated"}
```

`category` 또는 `title` 변경 시: 파일이 새 경로로 이동되고 이전 경로는 제거된다.
대상 경로에 파일이 이미 있으면 `FileExistsError`.

---

### `forget`

엔트리 아카이브 (소프트 삭제).

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | O | `"category/file.md"` |
| `reason` | string | - | 아카이브 이유 (파일에 HTML 주석으로 기록됨) |

**반환**: JSON

```json
{
  "path": "python/old-entry.md",
  "archived_to": "/Users/user/.ohkb/archive/python/old-entry.md",
  "status": "archived"
}
```

파일은 `archive/`로 이동된다. 동일 path를 다시 아카이브하면 타임스탬프 접미사로
이전 버전이 보존된다. 복원은 `restore` 사용.

---

### `restore`

아카이브된 엔트리를 wiki로 복원.

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `path` | string | - | 원본 wiki 경로 (최신 아카이브 복원) |
| `archive_path` | string | - | 특정 아카이브 상대 경로 |
| `overwrite` | boolean | - | 기존 wiki 파일 덮어쓰기 (기본 false) |

`path` 또는 `archive_path` 중 하나 필요.

**반환**: JSON

```json
{
  "path": "python/old-entry.md",
  "restored_from": "python/old-entry.md",
  "status": "restored"
}
```

---

## Prompts

### `research(topic)`

특정 주제를 KB에서 체계적으로 조사하는 워크플로우를 LLM에게 안내한다.

```
1. ohkb://index 읽기 (KB 구조 파악)
2. 키워드로 search (결과 없으면 동의어로 재시도)
3. 관련 엔트리를 get으로 읽기
4. 종합 답변 생성 (특정 엔트리 인용)
5. 정보 부족 시 명시
```

---

### `learn_from_text(text)`

텍스트 블록에서 지식을 추출하여 atomic 사실로 저장하는 워크플로우.

```
- 저장 전 search로 중복 확인
- 하나의 사실 = 하나의 엔트리 (3000자 미만)
- 태그 3-7개, 주요 동의어를 aliases로
- index의 기존 카테고리 재사용, 하위 주제는 중첩 경로
```

---

### `organize(category?)`

KB (또는 특정 카테고리)를 검토하고 정리하는 워크플로우.

```
1. lint로 이슈 확인
2. 태그/별칭 부족 엔트리 보완 (3-7개 태그, 주요 동의어)
3. 3000자 초과 엔트리 분할
4. 중복/유사 엔트리 확인
5. flat 카테고리 중첩 경로 검토 (python → python/stdlib)
6. 변경 요약 보고
```
