# SuperPikachu v2 구현 계획

## 설계 원칙 (이 문서 전체를 관통하는 규칙)

1. **시스템은 LLM을 호출하지 않는다** — 모든 시맨틱 판단은 LLM이 CLI를 호출하여 수행
2. **CLI가 canonical interface** — MCP, Web UI는 CLI(Brain) 위의 래퍼
3. **컨텍스트 비용 최소화** — 모든 설계 결정에서 토큰 소비량을 고려
4. **원자적 지식 단위** — 하나의 사실 = 하나의 파일 (권장 최대 3,000자)
5. **임베딩 대신 LLM이 tags/aliases 생성** — BM25 시맨틱 갭을 LLM이 메꿈

---

## Phase 0: Brain 클래스 (부트스트랩 통합)

### 목적
현재 3곳(mcp/server.py, api/app.py, cli/main.py)에 중복된 초기화 로직을 하나로 통합.

### 변경 대상

**새 파일: `src/superpikachu/brain.py`**

```python
class Brain:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else resolve_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(self.data_dir / META_DB)
        self.db.initialize()

        wiki_dir = self.data_dir / WIKI_DIR
        self.wiki = WikiManager(wiki_dir, self.db)
        self.raw = RawManager(self.data_dir)
        self.search_engine = SearchEngine(self.db, wiki_dir)
        self.conflicts = ConflictDetector(self.db)

        self.wiki.indexer.sync()

    def close(self):
        self.db.close()
```

이 클래스에 search, learn, edit, meta, forget, merge, db_exec, db_query,
db_schema, tree, status, lint 메서드를 모두 구현. 각 메서드는 dict를 반환.

### 기존 파일 수정

| 파일 | 변경 내용 |
|------|----------|
| `cli/main.py` | `_db()` 헬퍼 제거, `Brain` 인스턴스 사용으로 교체 |
| `mcp/server.py` | `create_server(brain)` 형태로 변경, 자체 부트스트랩 제거 |
| `api/app.py` | `create_app(brain)` 형태로 변경, 자체 부트스트랩 제거 |

### 중복 객체 제거
- `SearchEngine.__init__`이 자체 `RouterMd`를 생성하는 문제
  → Brain에서 `RouterMd`를 한 번만 생성하고 WikiManager, SearchEngine 모두에 주입
- `mcp/server.py`가 별도 `LogMd`를 생성하는 문제
  → WikiManager 내부의 `_log`를 사용

### `__init__.py` 수정

```python
from .brain import Brain
__version__ = "0.2.0"
```

---

## Phase 1: FTS5 스키마 변경 (aliases 컬럼 추가)

### 목적
LLM이 제공하는 동의어/유의어(aliases)를 검색에 반영하여 임베딩 없이 시맨틱 검색 품질 확보.

### 변경 대상

**`storage/database.py`** — `_SYSTEM_TABLES_SQL` 수정

```sql
-- 현재
CREATE VIRTUAL TABLE IF NOT EXISTS _knowledge USING fts5(
    path, category, title, content, tags, entity_type,
    tokenize='unicode61'
);

-- 변경
CREATE VIRTUAL TABLE IF NOT EXISTS _knowledge USING fts5(
    path, category, title, content, tags, aliases, entity_type,
    tokenize='unicode61'
);
```

스키마 마이그레이션:
- `SCHEMA_VERSION`을 1 → 2로 변경
- `database.py`의 `initialize()`에 마이그레이션 로직 추가:
  1. 현재 버전 확인
  2. v1이면: `_knowledge` 테이블 DROP → 재생성 (FTS5는 ALTER 불가)
  3. `_file_index` 전체 삭제 (reindex 강제)
  4. `_meta`의 `schema_version`을 2로 업데이트

**`constants.py`**

```python
SCHEMA_VERSION = 2
MAX_CONTENT_SIZE = 3000  # chars, 권장 최대 파일 크기 (신규)
TABLES_CATEGORY = "_tables"  # DB 테이블 문서용 카테고리 (신규)
```

**`storage/indexer.py`** — `index_file()` 수정

```python
# 현재 (66-69행)
self._db.execute(
    "INSERT INTO _knowledge (path, category, title, content, tags, entity_type) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    (rel_path, cat, title, body, tags, etype),
)

# 변경
aliases = ",".join(meta.get("aliases", []))
self._db.execute(
    "INSERT INTO _knowledge (path, category, title, content, tags, aliases, entity_type) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (rel_path, cat, title, body, tags, aliases, etype),
)
```

**`search/fts.py`** — BM25 가중치 변경

```python
# 현재 (24행)
bm25_weights = "1.0, 1.0, 5.0, 10.0, 3.0, 0.0"
# 컬럼:        path  cat   title content tags  entity_type

# 변경
bm25_weights = "1.0, 1.0, 5.0, 10.0, 3.0, 8.0, 0.0"
# 컬럼:        path  cat   title content tags  aliases entity_type
```

**`search/hierarchical.py`** — 동일하게 BM25 가중치 변경 (60행)

```python
# 현재
"bm25(_knowledge, 1.0, 1.0, 5.0, 10.0, 3.0, 0.0) as score "

# 변경
"bm25(_knowledge, 1.0, 1.0, 5.0, 10.0, 3.0, 8.0, 0.0) as score "
```

---

## Phase 2: frontmatter 변경 + learn 강화

### 목적
aliases 필드 추가, tags/aliases 미입력 시 경고, 원자적 지식 단위 권장.

### 변경 대상

**`storage/wiki.py`** — `_frontmatter()` 수정

```python
def _frontmatter(title: str, category: str, meta: dict | None = None) -> str:
    m = meta or {}
    now = datetime.now(timezone.utc).isoformat()
    tags = ", ".join(m.get("tags", []))
    aliases = ", ".join(m.get("aliases", []))     # 신규
    lines = [
        "---",
        f"title: {title}",
        f"category: {category}",
        f"tags: [{tags}]",
        f"aliases: [{aliases}]",                   # 신규
        f"source: {m.get('source', 'manual')}",
        f"entity_type: {m.get('entity_type', 'concept')}",
        f"created: {now}",
        f"updated: {now}",
    ]
    if m.get("temporal_expiry"):
        lines.append(f"temporal_expiry: {m['temporal_expiry']}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"
```

**`storage/wiki.py`** — `write_fact()` 수정

`--overwrite` 동작 추가. 현재는 동일 slug 파일이 있으면 append(섹션 추가)하지만,
overwrite=True이면 기존 파일을 통째로 교체:

```python
def write_fact(
    self,
    category: str,
    title: str,
    content: str,
    metadata: dict | None = None,
    overwrite: bool = False,          # 신규 파라미터
) -> WriteResult:
    self.ensure_category(category)
    slug = _slugify(title)
    cat_dir = self.dir / category
    target = self._find_or_create(cat_dir, slug, title, category, metadata)
    existed = target.exists()

    if existed and overwrite:
        # 통째로 교체
        text = _frontmatter(title, category, metadata)
        text += f"# {title}\n\n{content}\n"
        target.write_text(text)
        created = False
    elif existed and not overwrite:
        # 기존: append
        with open(target, "a") as f:
            f.write(f"\n## {title}\n\n{content}\n")
        self._touch_updated(target)
        created = False
    else:
        # 신규
        text = _frontmatter(title, category, metadata)
        text += f"# {title}\n\n{content}\n"
        target.write_text(text)
        created = True

    # ... (이후 인덱싱 로직 동일)
```

---

## Phase 3: edit (라인 단위 수정)

### 목적
기존 파일 수정 시 전체 내용을 다시 쓸 필요 없이, 변경할 라인만 지정.

### 구현 위치

**`brain.py`에 메서드 추가:**

```python
def get(self, path: str) -> dict:
    """파일 읽기. 라인 번호 포함."""
    content = self.wiki.read_file(path)
    if not content:
        return {"error": f"Not found: {path}"}
    lines = content.splitlines()
    numbered = "\n".join(f"{i+1:>3}: {line}" for i, line in enumerate(lines))
    return {
        "content": numbered,
        "total_lines": len(lines),
    }

def edit_lines(self, path: str, line: int = None, lines_range: str = None,
               new_content: str = None, after: int = None, delete: int = None) -> dict:
    """라인 단위 편집. 한 번에 하나의 작업만."""
    full = self.wiki.dir / path
    if not full.exists():
        return {"error": f"Not found: {path}"}

    all_lines = full.read_text().splitlines()

    if delete is not None:
        # 라인 삭제
        idx = delete - 1
        if 0 <= idx < len(all_lines):
            removed = all_lines.pop(idx)
            full.write_text("\n".join(all_lines) + "\n")
            self.wiki.indexer.index_file(path)
            return {"deleted_line": delete, "was": removed}

    if after is not None and new_content is not None:
        # 라인 뒤에 삽입
        idx = after  # after=5이면 5번째 줄 뒤 = index 5에 insert
        for i, new_line in enumerate(new_content.split("\\n")):
            all_lines.insert(idx + i, new_line)
        full.write_text("\n".join(all_lines) + "\n")
        self.wiki.indexer.index_file(path)
        return {"inserted_after": after, "lines_added": len(new_content.split("\\n"))}

    if line is not None and new_content is not None:
        # 한 줄 교체
        idx = line - 1
        if 0 <= idx < len(all_lines):
            old = all_lines[idx]
            all_lines[idx] = new_content
            full.write_text("\n".join(all_lines) + "\n")
            self.wiki.indexer.index_file(path)
            return {"replaced_line": line, "was": old, "now": new_content}

    if lines_range is not None and new_content is not None:
        # 범위 교체 (예: "10-12")
        start, end = [int(x) for x in lines_range.split("-")]
        old = all_lines[start-1:end]
        new_lines = new_content.split("\\n")
        all_lines[start-1:end] = new_lines
        full.write_text("\n".join(all_lines) + "\n")
        self.wiki.indexer.index_file(path)
        return {"replaced_lines": f"{start}-{end}", "was": old, "now": new_lines}

    return {"error": "Invalid edit parameters"}
```

**라인 교체 후 자동 reindex 포함** — 별도 reindex 명령 불필요.

### 컨텍스트 비용 분석

11줄 파일에서 1줄 수정:
- `brain get "path"` → ~120 토큰 (라인번호 포함 전체 출력)
- `brain edit "path" --line 10 "새 내용"` → ~30 토큰
- 총 ~150 토큰 (vs 기존 방식 ~250 토큰)

50줄 파일에서 1줄 수정:
- `brain get` → ~500 토큰
- `brain edit --line` → ~30 토큰  
- 총 ~530 토큰 (vs 기존 방식 ~1,000 토큰)

---

## Phase 4: meta (메타데이터 수정)

### 목적
frontmatter(tags, aliases, title, category 등)를 파일 내용을 읽지 않고 수정.

### 구현 위치

**`brain.py`에 메서드 추가:**

```python
def meta(self, path: str, title: str = None, category: str = None,
         add_tags: list[str] = None, remove_tags: list[str] = None,
         add_aliases: list[str] = None, remove_aliases: list[str] = None,
         entity_type: str = None) -> dict:
    full = self.wiki.dir / path
    if not full.exists():
        return {"error": f"Not found: {path}"}

    text = full.read_text()
    meta, body = _parse_front(text)  # indexer.py의 _parse_front 재사용

    changes = {}

    if title is not None:
        meta["title"] = title
        changes["title"] = title

    if add_tags:
        existing = meta.get("tags", [])
        if isinstance(existing, str):
            existing = [existing] if existing else []
        new_tags = list(dict.fromkeys(existing + add_tags))  # 중복 제거, 순서 유지
        meta["tags"] = new_tags
        changes["tags"] = new_tags

    if remove_tags:
        existing = meta.get("tags", [])
        if isinstance(existing, str):
            existing = [existing] if existing else []
        meta["tags"] = [t for t in existing if t not in remove_tags]
        changes["tags"] = meta["tags"]

    if add_aliases:
        existing = meta.get("aliases", [])
        if isinstance(existing, str):
            existing = [existing] if existing else []
        new_aliases = list(dict.fromkeys(existing + add_aliases))
        meta["aliases"] = new_aliases
        changes["aliases"] = new_aliases

    if remove_aliases:
        existing = meta.get("aliases", [])
        if isinstance(existing, str):
            existing = [existing] if existing else []
        meta["aliases"] = [a for a in existing if a not in remove_aliases]
        changes["aliases"] = meta["aliases"]

    if entity_type is not None:
        meta["entity_type"] = entity_type
        changes["entity_type"] = entity_type

    # frontmatter 재생성 + body 결합
    new_text = _frontmatter(meta.get("title", ""), meta.get("category", ""), meta)
    new_text += body
    full.write_text(new_text)

    # category 변경 시 파일 이동
    if category is not None and category != meta.get("category"):
        old_path = path
        new_dir = self.wiki.dir / category
        new_dir.mkdir(exist_ok=True)
        new_file = new_dir / full.name
        full.rename(new_file)
        self.wiki.indexer.remove_file(old_path)
        new_path = f"{category}/{full.name}"
        self.wiki.indexer.index_file(new_path)
        changes["moved"] = {"from": old_path, "to": new_path}
        self.wiki.ensure_category(category)
        return {"changes": changes, "path": new_path}

    self.wiki.indexer.index_file(path)
    return {"changes": changes, "path": path}
```

### 컨텍스트 비용

```
brain meta "path" --add-tags "PEP-703" → ~30 토큰
```

파일 내용(body)을 LLM 컨텍스트에 넣을 필요가 전혀 없음.
시스템이 내부적으로 frontmatter만 파싱/수정/저장.

---

## Phase 5: DB 테이블 자동 문서화 (`_tables/`)

### 목적
DB 테이블마다 Wiki MD 설명서를 자동 생성하여, `brain search`로 DB 관련 질문도 매칭.

### 구현 위치

**`brain.py`에 내부 메서드 추가:**

```python
def _sync_table_doc(self, table_name: str) -> str:
    """사용자 테이블에 대한 _tables/{name}.md 자동 생성/갱신."""
    cols = self.db.table_info(table_name)
    row_cnt = self.db.row_count(table_name)

    col_lines = "| column | type | pk |\n|--------|------|----|\n"
    col_names = []
    for c in cols:
        pk = "PK" if c["pk"] else ""
        col_lines += f"| {c['name']} | {c['type']} | {pk} |\n"
        col_names.append(c['name'])

    content = f"## Schema\n\n{col_lines}\n"
    content += f"## Stats\n\n{row_cnt} rows.\n\n"
    content += f"## Example Queries\n\n"
    content += f"```sql\nSELECT * FROM {table_name} LIMIT 5\n```\n"

    meta = {
        "tags": col_names + [table_name],
        "aliases": [],  # LLM이 나중에 brain meta로 보강
        "entity_type": "db-table",
        "source": "auto",
    }

    result = self.wiki.write_fact(
        TABLES_CATEGORY,
        f"{table_name} table",
        content,
        meta,
        overwrite=True,
    )
    return result.path
```

**`brain.py`의 `db_exec()` 메서드에서 DDL 감지 시 호출:**

```python
def db_exec(self, sql: str, params: list = None) -> dict:
    parsed = _parse_sql(sql)
    tbl = parsed["table"]

    if tbl and self.db.is_system_table(tbl):
        return {"error": f"System table '{tbl}' is protected."}

    try:
        cur = self.db.execute(sql, tuple(params or []))
        self.db.commit()

        if parsed["is_ddl"]:
            self.db.log_ddl(sql, tbl, parsed["action"], True)
            # DDL 후 자동 문서화
            if parsed["action"] in ("CREATE", "ALTER"):
                doc_path = self._sync_table_doc(tbl)
            elif parsed["action"] == "DROP":
                doc_path = f"{TABLES_CATEGORY}/{_slugify(tbl + ' table')}.md"
                self.wiki.archive_file(doc_path, reason="table dropped")

        return {"affected_rows": cur.rowcount, "result": "ok"}
    except Exception as e:
        if parsed["is_ddl"]:
            self.db.log_ddl(sql, tbl, parsed["action"], False)
        return {"error": str(e)}
```

### 흐름

```
LLM: brain db exec "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, plan TEXT)"
  → 테이블 생성
  → _tables/customers-table.md 자동 생성
  → FTS5에 색인 (tags에 컬럼명 포함)

나중에:
LLM: brain search "고객 요금제"
  → _tables/customers-table.md 매칭 (tags에 "plan" 있으므로)
  → LLM이 읽고 "아, customers 테이블이 있구나"
  → brain db query "SELECT plan FROM customers WHERE name LIKE '%Acme%'"
```

### `_tables/` 문서에서 LLM이 직접 보강 가능

```bash
# 자동 생성된 후 LLM이 aliases 추가
brain meta "_tables/customers-table.md" \
  --add-aliases "고객 목록,거래처 DB,client list"

# 설명 보강 (사용법 노트 추가)
brain edit "_tables/customers-table.md" --after 12 \
  "plan 컬럼 값: free, pro, enterprise. trial 중인 경우 free + trial_ends IS NOT NULL."
```

### INSERT/UPDATE 시

데이터 추가/수정 시에는 `_tables/` 문서를 건드리지 않음.
row_count만 달라지지만, 이건 `brain db schema`나 `brain status`에서 실시간 조회 가능.
문서의 row count는 stale해질 수 있으나, 정확한 수치는 항상 DB에서 직접 조회.

---

## Phase 6: extract 패키지 통합 + learn-util

### 목적
3곳에 중복된 텍스트 추출/URL 크롤링 로직을 extract/ 패키지로 통합.
learn-util CLI 명령으로 청크 기반 출력 제공.

### 변경 대상

**빈 `extract/__init__.py` 에 구현 추가**

**새 파일: `extract/text.py`**

```python
def extract_text(file_path: Path) -> str:
    """파일에서 텍스트 추출. 현재 mcp/tools_learn.py 50-72행의 로직 이동."""
    ext = file_path.suffix.lower()
    if ext in (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml", ".xml"):
        return file_path.read_text(errors="replace")
    elif ext == ".pdf":
        import fitz
        doc = fitz.open(str(file_path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    elif ext == ".docx":
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(para.text for para in doc.paragraphs)
    elif ext in (".html", ".htm"):
        from markdownify import markdownify
        html = file_path.read_text(errors="replace")
        return markdownify(html)
    else:
        return file_path.read_text(errors="replace")
```

**새 파일: `extract/url.py`**

```python
async def fetch_url(url: str) -> dict:
    """URL 크롤링 + HTML→MD 변환. 현재 mcp/tools_learn.py 84-113행의 로직 이동."""
    import httpx
    from bs4 import BeautifulSoup
    from markdownify import markdownify
    from urllib.parse import urlparse

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup.body or soup
    md = markdownify(str(article))
    title = soup.title.string if soup.title else urlparse(url).path

    return {"text": md, "title": str(title), "domain": urlparse(url).netloc}
```

**새 파일: `extract/chunker.py`**

```python
def chunk_text(text: str, max_chunk_chars: int = 2000) -> list[dict]:
    """텍스트를 단락/헤딩 경계 기준으로 청크 분할."""
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chunk_chars and current:
            chunks.append({
                "index": len(chunks),
                "text": "\n\n".join(current),
                "chars": current_len,
            })
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append({
            "index": len(chunks),
            "text": "\n\n".join(current),
            "chars": current_len,
        })

    return chunks
```

### learn-util CLI 출력

```bash
brain learn-util doc report.pdf
```

기본 출력: 처음 2개 청크는 전문, 나머지는 처음 500자만 (truncated 표시).

```
Source: report.pdf (PDF, 48,231 bytes)
Chunks: 5 total

--- Chunk 1/5 (2,134 chars) ---
Python 3.13 introduces an experimental free-threaded build
that allows disabling the GIL. This is based on PEP 703...
(전문)

--- Chunk 2/5 (1,987 chars) ---
The free-threaded build can be enabled with ./configure
--disable-gil. Performance benchmarks show...
(전문)

--- Chunk 3/5 (2,401 chars, showing first 500) ---
Thread safety changes include: new per-object locks...
(truncated, use: brain learn-util doc report.pdf --chunk 3)

--- Chunk 4/5 (1,856 chars, showing first 500) ---
...
--- Chunk 5/5 (980 chars, showing first 500) ---
...
```

옵션:
- `--chunk N`: N번째 청크 전문 출력
- `--all`: 전체 출력 (경고 포함)
- `--json`: JSON 형태 출력

### 기존 코드에서 중복 제거

| 위치 | 변경 |
|------|------|
| `mcp/tools_learn.py` 50-72행 | `extract.text.extract_text()` 호출로 교체 |
| `mcp/tools_learn.py` 84-113행 | `extract.url.fetch_url()` 호출로 교체 |
| `api/app.py` `_extract_text()` | `extract.text.extract_text()` 호출로 교체 |
| `api/app.py` `_fetch_url()` | `extract.url.fetch_url()` 호출로 교체 |

---

## Phase 7: CLI 전면 확장

### 목적
Brain의 모든 메서드를 CLI 명령으로 노출. 기본 MD 출력 + `--json` 플래그.

### 현재 CLI 명령 (5개)
- `serve`, `search`, `status`, `tree`, `init`

### 추가할 CLI 명령

```python
# 읽기 (라인 번호 포함)
@cli.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
def get(path, as_json):
    """Read a knowledge file with line numbers."""

# 지식 저장
@cli.command()
@click.argument("content")
@click.option("--title", "-t", required=True)
@click.option("--category", "-c", required=True)
@click.option("--tags", default="")
@click.option("--aliases", default="")
@click.option("--entity-type", default="concept")
@click.option("--source", default="manual")
@click.option("--overwrite", is_flag=True)
@click.option("--file", "-f", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True)
def learn(content, title, category, tags, aliases, entity_type, source, overwrite, file, as_json):
    """Store knowledge. Warns if --tags or --aliases missing."""
    # tags/aliases 미입력 시 stderr 경고
    if not tags:
        click.echo("Warning: No --tags provided. Search quality may be limited.", err=True)
        click.echo('Consider: --tags "keyword1,keyword2"', err=True)
    if not aliases:
        click.echo("Warning: No --aliases provided. Semantic matching will be limited.", err=True)
        click.echo('Consider: --aliases "synonym1,synonym2"', err=True)
    # content가 빈 문자열이고 --file이 있으면 파일에서 읽기
    # 또는 stdin이 tty가 아니면 stdin에서 읽기

# 라인 편집
@cli.command()
@click.argument("path")
@click.option("--line", type=int)
@click.option("--lines", type=str)  # "10-15"
@click.option("--after", type=int)
@click.option("--delete", type=int)
@click.argument("new_content", required=False)
@click.option("--json", "as_json", is_flag=True)
def edit(path, line, lines, after, delete, new_content, as_json):
    """Edit specific lines of a knowledge file."""

# 메타데이터 수정
@cli.command()
@click.argument("path")
@click.option("--title")
@click.option("--category")
@click.option("--add-tags")
@click.option("--remove-tags")
@click.option("--add-aliases")
@click.option("--remove-aliases")
@click.option("--entity-type")
@click.option("--json", "as_json", is_flag=True)
def meta(path, title, category, add_tags, remove_tags, add_aliases, remove_aliases, entity_type, as_json):
    """Modify file metadata (tags, aliases, title, category)."""

# 아카이브
@cli.command()
@click.argument("path")
@click.option("--reason", default="")
@click.option("--json", "as_json", is_flag=True)
def forget(path, reason, as_json):
    """Archive a knowledge file."""

# 충돌 해결
@cli.command()
@click.argument("conflict_id", type=int)
@click.argument("resolution")
@click.option("--json", "as_json", is_flag=True)
def merge(conflict_id, resolution, as_json):
    """Resolve a conflict."""

# 건강 체크
@cli.command()
@click.option("--json", "as_json", is_flag=True)
def lint(as_json):
    """Health check. Reports conflicts, stale, oversized, missing tags/aliases."""

# learn-util (서브그룹)
@cli.group("learn-util")
def learn_util():
    """Extract text from documents/URLs for learning."""

@learn_util.command("doc")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--chunk", type=int, default=None)
@click.option("--all", "show_all", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def learn_util_doc(file_path, chunk, show_all, as_json):
    """Extract text from a document file."""

@learn_util.command("url")
@click.argument("url")
@click.option("--chunk", type=int, default=None)
@click.option("--all", "show_all", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def learn_util_url(url, chunk, show_all, as_json):
    """Fetch and extract text from a URL."""

# DB (서브그룹)
@cli.group()
def db():
    """Database operations."""

@db.command("exec")
@click.argument("sql")
@click.option("--json", "as_json", is_flag=True)
def db_exec(sql, as_json):
    """Execute DDL/DML. Auto-generates _tables/ docs on schema changes."""

@db.command("query")
@click.argument("sql")
@click.option("--json", "as_json", is_flag=True)
def db_query(sql, as_json):
    """Execute SELECT query."""

@db.command("schema")
@click.option("--table", default=None)
@click.option("--json", "as_json", is_flag=True)
def db_schema(table, as_json):
    """Show database schema."""

# Web UI
@cli.command()
@click.option("--port", default=7777)
def web(port):
    """Start Web UI server."""
```

### lint 확장: tags/aliases 누락 + 파일 크기 경고

```python
def lint(self) -> dict:
    issues = []

    # 충돌
    pending = self.conflicts.list_pending()
    for c in pending:
        issues.append({"type": "conflict", "path": c["knowledge_path_a"], ...})

    # 파일 크기 초과
    oversized = self.db.query(
        "SELECT path, size FROM _file_index WHERE size > ?",
        (MAX_CONTENT_SIZE * 3,)  # 3000자 * ~3 bytes
    )
    for r in oversized:
        issues.append({"type": "oversized", "path": r["path"], "size": r["size"],
                        "suggestion": "Consider splitting into smaller documents."})

    # tags/aliases 누락
    rows = self.db.query(
        "SELECT path, tags, aliases FROM _knowledge WHERE category != ?",
        (TABLES_CATEGORY,)
    )
    for r in rows:
        if not r["tags"]:
            issues.append({"type": "no_tags", "path": r["path"]})
        if not r["aliases"]:
            issues.append({"type": "no_aliases", "path": r["path"]})

    # stale (30일 미사용)
    # ... (기존 로직 유지)

    return {"issues": issues, "total": len(issues)}
```

---

## Phase 8: MCP 서버 리팩토링

### 목적
MCP 도구들이 Brain 메서드를 직접 호출하도록 변경. 중복 로직 제거.

### 변경 대상

**`mcp/server.py`**

```python
def create_server(brain: Brain | None = None) -> tuple[FastMCP, Brain]:
    if brain is None:
        brain = Brain()

    srv = FastMCP("superpikachu")
    tools_knowledge.register(srv, brain)
    tools_learn.register(srv, brain)
    tools_manage.register(srv, brain)
    tools_db.register(srv, brain)

    return srv, brain


def main():
    brain = Brain()
    srv, _ = create_server(brain)
    srv.run(transport="stdio")
```

**`mcp/tools_knowledge.py`** — 예시

```python
def register(server: FastMCP, brain: Brain):

    @server.tool()
    async def knowledge_search(query: str, max_results: int = 10,
                               category: str | None = None) -> dict:
        """Search the knowledge base."""
        return brain.search(query, max_results=max_results, category=category)

    @server.tool()
    async def knowledge_get(path: str) -> dict:
        """Read a knowledge file with line numbers."""
        return brain.get(path)
    # ...
```

**`mcp/tools_learn.py`** — learn_fact에 aliases 파라미터 추가

```python
@server.tool()
async def learn_fact(
    category: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,     # 신규
    entity_type: str = "concept",
    source: str = "manual",
    overwrite: bool = False,               # 신규
) -> dict:
    """Store a fact. Always provide tags and aliases for searchability."""
    metadata = {
        "tags": tags or [],
        "aliases": aliases or [],
        "entity_type": entity_type,
        "source": source,
    }
    return brain.learn(content, title, category, metadata, overwrite)
```

**tools_config.py 제거** — config는 CLI 전용 기능으로. MCP에서는 불필요.

---

## Phase 9: pyproject.toml 의존성 재구성

### 변경

```toml
[project]
dependencies = [
    # core: CLI + Brain만 사용할 때 필요한 것
    "pyyaml>=6.0",
    "click>=8.1",
]

[project.optional-dependencies]
mcp = ["mcp>=1.0"]
crawl = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "markdownify>=0.13",
]
extract = [
    "pymupdf>=1.24",
    "python-docx>=1.1",
    "openpyxl>=3.1",
]
web = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
]
all = [
    "superpikachu[mcp,crawl,extract,web]",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.5",
]
```

### 핵심 변경
- `mcp>=1.0`이 core 의존성에서 optional로 이동
- `httpx`, `beautifulsoup4`, `markdownify`가 core에서 `[crawl]`로 이동
- core 설치 시: `pyyaml` + `click`만 필요 (매우 경량)

### lazy import 처리

`mcp/` 패키지는 `import mcp`를 모듈 레벨에서 하므로, MCP를 설치하지 않은
상태에서 `from superpikachu.mcp import ...` 하면 ImportError 발생.
이건 의도적 동작이며, CLI에서 `brain serve`를 할 때만 발생:

```python
@cli.command()
def serve():
    """Start MCP server (stdio)."""
    try:
        from ..mcp.server import main
        main()
    except ImportError:
        click.echo("MCP not installed. Run: pip install superpikachu[mcp]", err=True)
```

---

## Phase 10: Skills 파일 작성

### 목적
LLM 에이전트가 brain CLI를 올바르게 사용하도록 가이드.

### 파일: `skills/BRAIN.md`

핵심 내용:

1. **명령어 레퍼런스** — 모든 CLI 명령 + 옵션 + 예시
2. **워크플로우 가이드:**
   - 새 지식 학습 (대화 중 발견 → learn)
   - 문서에서 학습 (learn-util doc → 읽기 → learn 반복)
   - URL에서 학습 (learn-util url → 읽기 → learn 반복)
   - 기존 지식 수정 (search → get → edit/meta)
   - DB 테이블 생성/조회 (db exec → 자동 문서화 → search로 발견)
   - 건강 체크 (lint → 문제 해결)
3. **핵심 규칙:**
   - 항상 tags + aliases를 넣어라
   - 하나의 사실 = 하나의 파일 (3,000자 이하 권장)
   - learn 전에 search로 중복 확인
   - 서술형 → learn, 구조화 → db exec
   - DB 테이블 설명서는 자동 생성되지만, aliases는 직접 추가해라
4. **LLM이 임베딩을 대체하는 방법:**
   - tags: 이 지식의 정확한 키워드
   - aliases: 이 지식을 다른 말로 표현하면? (동의어, 유의어, 약어)
   - 예시: "GIL 비활성화" → aliases: "nogil, no-GIL, free-threading, 멀티스레딩 개선"

---

## 작업 순서 및 의존성

```
Phase 0: Brain 클래스
    │
    ├─→ Phase 1: FTS5 aliases (Brain.db 사용)
    │       │
    │       └─→ Phase 2: frontmatter + learn --overwrite
    │
    ├─→ Phase 3: edit (Brain.edit_lines)
    │
    ├─→ Phase 4: meta (Brain.meta)
    │
    ├─→ Phase 5: _tables/ 자동문서 (Brain.db_exec 내부)
    │
    └─→ Phase 6: extract 패키지 (Brain과 무관, 독립)

Phase 0~6 완료 후:
    Phase 7: CLI 전면 확장 (Brain의 모든 메서드를 CLI로)
    Phase 8: MCP 리팩토링 (Brain 주입)
    Phase 9: pyproject.toml (의존성 분리)
    Phase 10: Skills 파일
```

### 예상 작업량

| Phase | 신규 파일 | 수정 파일 | 예상 라인 | 난이도 |
|-------|----------|----------|----------|--------|
| 0 | brain.py | cli/main.py, mcp/server.py, __init__.py | ~150 | 중 |
| 1 | - | database.py, constants.py, indexer.py, fts.py, hierarchical.py | ~30 | 저 |
| 2 | - | wiki.py | ~30 | 저 |
| 3 | - | brain.py | ~60 | 저 |
| 4 | - | brain.py | ~80 | 중 |
| 5 | - | brain.py, constants.py | ~50 | 중 |
| 6 | extract/text.py, extract/url.py, extract/chunker.py | mcp/tools_learn.py, api/app.py | ~120 | 중 |
| 7 | - | cli/main.py (전면 재작성) | ~300 | 고 |
| 8 | - | mcp/server.py, tools_*.py (전부) | ~150 | 중 |
| 9 | - | pyproject.toml | ~10 | 저 |
| 10 | skills/BRAIN.md | - | ~200 | 중 |

**총 예상: 신규 ~4파일, 수정 ~15파일, ~1,180 라인 추가/변경**

---

## 테스트 계획

### 각 Phase 완료 후 검증

| Phase | 검증 방법 |
|-------|----------|
| 0 | `from superpikachu import Brain; b = Brain("/tmp/test"); b.close()` |
| 1 | `brain init && brain learn "test" -t "t" -c "c" --aliases "a1"` → FTS5에 aliases 색인 확인 |
| 2 | `brain learn ... --overwrite` → 기존 파일 교체 확인 |
| 3 | `brain get "path"` → 라인번호 출력 확인, `brain edit --line` → 변경 확인 |
| 4 | `brain meta --add-tags` → frontmatter 변경 확인, `--category` → 파일 이동 확인 |
| 5 | `brain db exec "CREATE TABLE ..."` → `_tables/` 문서 자동 생성 확인 |
| 6 | `brain learn-util doc sample.pdf` → 청크 출력 확인 |
| 7 | 전체 CLI 명령 수동 통합 테스트 |
| 8 | MCP inspector로 도구 호출 테스트 |
| 9 | `pip install .` → core만 설치 확인, `pip install .[mcp]` → MCP 포함 확인 |
| 10 | Skills 파일을 Claude Code에 넣고 실제 사용 테스트 |

### 기존 E2E 테스트 호환성
현재 `tests/` 디렉토리의 58개 E2E 테스트가 MCP 도구 기반.
Phase 8(MCP 리팩토링) 후에 전부 통과해야 함.
Brain 메서드 기반 유닛 테스트를 Phase별로 추가.
