# Search Engine Design

## Principle: No Embeddings, No Vector DB

임베딩/벡터 DB 없이 3가지 검색 전략을 조합하여 사용.
LLM이 쿼리 성격을 판단하여 적절한 도구(knowledge_search vs db_query)를 선택.

## Strategy A: Hierarchical BM25 (계층적 탐색)

기본 전략. 3단계로 탐색 범위를 좁혀가며 검색.

```
쿼리: "Python 리스트 컴프리헨션"
      │
      ▼
[1단계: 카테고리 매칭]
  _router.md의 각 카테고리 설명(텍스트) vs 쿼리를 BM25 매칭
  → score: {programming: 0.82, personal: 0.05, projects: 0.12}
  → "programming" 선택
      │
      ▼
[2단계: 파일 매칭]
  wiki/programming/_index.md의 파일별 키워드/설명 vs 쿼리를 BM25 매칭
  → score: {python-basics.md: 0.91, git.md: 0.03, api-design.md: 0.15}
  → "python-basics.md" 선택
      │
      ▼
[3단계: 섹션 매칭]
  wiki/programming/python-basics.md를 청크로 나누어 FTS5 검색
  → "## 리스트 컴프리헨션" 섹션이 가장 높은 점수
      │
      ▼
[결과 반환]
  path: "programming/python-basics.md"
  section: "## 리스트 컴프리헨션"
  snippet: "리스트 컴프리헨션은 기존 리스트에서..."
  score: 0.91
```

장점:
- 전체 스캔 절대 안 함. 수십만 파일이어도 실제 읽는 건 2~3개
- 토큰 비용 0, LLM 호출 0
- 속도 < 10ms

한계:
- 카테고리가 잘못 매칭되면 결과 누락 가능
- → 전략 C로 폴백

## Strategy B: SQL Structured Query (구조 검색)

LLM이 db_query를 직접 호출. 구조화된 데이터에 적합.

```
쿼리: "활성 상태인 Python 프로젝트 뭐 있어?"
      │
      ▼
LLM 판단: "이건 구조화 쿼리다"
      │
      ▼
LLM → db_query("SELECT name, md_path FROM projects 
                 WHERE language='Python' AND status='active'")
      │
      ▼
결과: [{name:"My App", md_path:"wiki/projects/my-app.md"}]
      │
      ▼
LLM → knowledge_get(path="projects/my-app.md")
      │
      ▼
상세 내용과 함께 답변 생성
```

장점:
- 정확한 필터/정렬/집계 가능
- < 5ms
- LLM이 SQL을 자유롭게 작성하므로 유연

전제:
- LLM이 해당 테이블을 이미 만들어둔 상태여야 함
- db_schema로 현재 스키마를 확인 가능

## Strategy C: Global FTS5 (전체 검색, 폴백)

_knowledge 테이블 전체에서 FTS5 검색. 카테고리를 모를 때 사용.

```
쿼리: 카테고리 매칭 실패 또는 cross-domain 검색
      │
      ▼
SELECT path, category, title, 
       bm25(_knowledge) as score,
       snippet(_knowledge, 3, '<b>', '</b>', '...', 64) as snippet
FROM _knowledge
WHERE _knowledge MATCH '{query}'
ORDER BY score
LIMIT {max_results}
      │
      ▼
결과 반환 (모든 카테고리에서)
```

장점:
- 놓치는 결과 없음
- 수백만 행에서도 < 50ms (FTS5 역색인)

단점:
- 계층적 탐색보다 느림 (전체 인덱스 스캔)
- 결과가 너무 많을 수 있음 → max_results로 제한

## Score Enhancement

### 리콜 빈도 가중

검색 결과에 리콜 빈도를 반영하여 최종 점수 산출.

```
final_score = bm25_score * (1 + log(1 + recall_count) * 0.1)
```

자주 리콜되는 지식이 약간 더 높은 점수를 받음.
OpenClaw Dreaming의 frequency 신호에서 영감.

### 시간 감쇠 (선택)

temporal_expiry가 설정된 지식에 대해 만료일 기반 감쇠.
config로 활성화 가능.

```
if temporal_expiry:
  days_until_expiry = (expiry_date - now).days
  if days_until_expiry < 0:
    → archive로 이동 (검색에서 제외)
  elif days_until_expiry < 7:
    score *= 0.5  (곧 만료되는 지식은 점수 감소)
```

### Stale 감쇠 (선택)

오래 리콜되지 않은 지식에 약한 패널티.

```
days_since_recall = (now - last_recalled).days
if days_since_recall > stale_threshold:
  score *= max(0.5, 1 - (days_since_recall - stale_threshold) / 365)
```

## Scale Projections

| 파일 수 | FTS5 행 수 | 인덱스 크기 | 검색 전략 | 예상 속도 |
|---------|-----------|------------|----------|----------|
| ~100 | ~1,000 | < 1MB | A (계층적) | < 5ms |
| ~1,000 | ~10,000 | < 10MB | A + C 병행 | < 20ms |
| ~10,000 | ~100,000 | < 100MB | C (FTS5 주력) | < 50ms |
| ~100,000 | ~1,000,000 | < 1GB | C + 샤딩 | < 100ms |
| ~1,000,000 | ~10,000,000 | ~10GB | C + 샤딩 + 파티셔닝 | < 200ms |

### 샤딩 전략 (대규모)

100,000+ 파일 시:
1. 카테고리별 별도 SQLite DB 파일 생성
2. `_meta.db`는 메타데이터/라우팅만 담당
3. 검색 시 관련 카테고리 DB만 쿼리
4. 카테고리 간 검색은 parallel query

## FTS5 Configuration

```sql
-- 기본 토크나이저: unicode61 (대부분의 언어 지원)
CREATE VIRTUAL TABLE _knowledge USING fts5(
  path, category, title, content, tags, entity_type,
  tokenize='unicode61'
);

-- CJK(한중일) 지원이 필요한 경우 trigram 토크나이저 고려
-- trigram은 더 느리지만 CJK 짧은 토큰도 검색 가능
-- config로 선택 가능하게
```

## Conflict Detection (충돌 감지)

learn_fact에서 새 지식 저장 시 기존 지식과의 충돌을 감지.

```
새 지식: "VS Code 사용"
      │
      ▼
FTS5에서 관련 키워드로 기존 지식 검색
  → "Vim 사용" 발견 (같은 카테고리, 유사 태그)
      │
      ▼
겹침 판단:
  - 같은 카테고리인가? ✓
  - 키워드 겹침이 높은가? ✓ (editor, 사용)
  - 내용이 상반되는가? → 시스템은 판단 불가
      │
      ▼
_conflicts에 기록 (type: "potential")
LLM에게 반환: "기존에 'Vim 사용' 지식이 있습니다. 충돌일 수 있습니다."
LLM이 판단하여 knowledge_merge 또는 무시
```

충돌 감지는 키워드 겹침 기반의 "후보 제안"이며,
실제 모순 여부 판단은 LLM에게 위임. (시스템은 LLM을 호출하지 않으므로)
