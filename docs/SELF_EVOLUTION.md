# Self-Evolution Mechanisms

## Overview

SuperPikachu의 자가진화는 5가지 축으로 구성된다.
핵심: **시스템은 감지/기록/보고만 하고, 판단/실행은 LLM이 한다.**

```
1. 학습 (Learn)     → 다양한 소스에서 지식 흡수
2. 정리 (Organize)  → 계층 구조 자동 생성/유지
3. 갱신 (Update)    → 충돌 감지, 모순 해결, 자동 망각
4. 확장 (Expand)    → 빈 곳 인식 → LLM이 스스로 연구
5. 복리 (Compound)  → 질문의 답도 위키에 재투입
```

## 1. 학습 (Learn)

### 소스별 학습 경로

| 소스 | 도구 | 시스템이 하는 일 | LLM이 하는 일 |
|------|------|----------------|-------------|
| 대화 | learn_fact | 저장, 인덱싱, 충돌검사 | 사실 추출, 분류, 카테고리 결정 |
| 문서 | learn_document | 텍스트 추출, 원본 보존 | 읽기, 요약, 분류, learn_fact 호출 |
| 웹 | learn_url | 크롤링, MD 변환, 원본 보존 | 읽기, 핵심 추출, learn_fact 호출 |
| 직접 입력 | learn_fact | 저장, 인덱싱 | 사용자가 직접 지시 |

### bluewater 교훈 적용: "타입별로 분류한 후 추출하라"

문서 흡수 시 LLM이 타입을 먼저 분류하고, 타입별 다른 전략으로 추출.
시스템은 이를 강제하지 않지만, MCP 도구 설명(description)에서 이 패턴을 권장.

```
learn_document 도구 설명에 포함:
"문서를 받으면 먼저 타입을 분류하세요 (보고서/논문/메모/대화록 등).
 타입에 따라 다른 구조로 learn_fact를 호출하는 것을 권장합니다.
 예: 보고서 → 요약 + 핵심 발견 + 방법론
     논문 → 초록 + 기여 + 한계 + 관련 연구
     대화록 → 결정 사항 + 액션 아이템"
```

## 2. 정리 (Organize)

### 카테고리 자동 생성

```
learn_fact(category="machine-learning", ...) 호출 시:
  wiki/machine-learning/ 폴더가 없으면:
    1. mkdir wiki/machine-learning/
    2. wiki/machine-learning/_index.md 생성 (빈 템플릿)
    3. _router.md에 카테고리 추가
    4. _categories 테이블에 등록
```

### _router.md 자동 갱신

카테고리 생성/삭제/변경 시 _router.md가 자동으로 갱신됨.
LLM이 knowledge_reorganize로 카테고리 설명을 개선할 수도 있음.

### _index.md 자동 갱신

파일 추가/수정/삭제 시 해당 카테고리의 _index.md가 갱신.
내용: 파일 목록, 키워드, 요약, 리콜 수, 최종 갱신일.

### 자동 분할 권고

knowledge_lint에서 감지:
- 파일 100KB 초과 → "이 파일을 분할하는 것을 권장합니다" 
- 폴더 200파일 초과 → "서브카테고리를 만드는 것을 권장합니다"
- 실제 분할 실행은 LLM이 knowledge_reorganize 호출

## 3. 갱신 (Update)

### 충돌 감지

learn_fact 시 자동으로 기존 지식과 키워드 겹침 검사.

```
감지 기준:
  1. 같은 카테고리 내 파일
  2. 태그 겹침률 > 50%
  3. FTS5 BM25 점수 > 임계값

감지되면:
  → _conflicts 테이블에 기록 (status: pending)
  → learn_fact 결과에 conflict 정보 포함
  → LLM이 판단하여:
    a. knowledge_merge로 병합
    b. knowledge_update로 기존 지식 수정
    c. 무시 (서로 다른 내용이라면)
```

### 충돌 해결 (LLM 위임)

```
LLM → knowledge_merge(
  conflict_id=1,
  resolution="VS Code로 전환함. 과거에는 Vim 사용",
  keep="custom"
)

시스템:
  1. 두 지식 항목을 하나로 병합 (LLM이 제공한 resolution 사용)
  2. _conflicts 상태를 resolved로 변경
  3. FTS5 인덱스 갱신
  4. _log.md에 기록
```

### 자동 망각

temporal_expiry가 설정된 지식:
- 만료일 지나면 자동으로 archive/로 이동
- FTS5 인덱스에서 제거
- _log.md에 기록
- knowledge_lint에서도 만료 지식 보고

### karesansui-u 인사이트: "모순 축적 = 성능 저하"

모순이 쌓이면 LLM이 컨텍스트에서 상반되는 정보를 받게 되어 답변 품질이 떨어짐.
이를 방지하기 위해:
1. 충돌 감지를 적극적으로 수행
2. knowledge_lint에서 미해결 충돌을 항상 최상단에 보고
3. 충돌이 N개 이상 쌓이면 knowledge_status에서 경고

## 4. 확장 (Expand)

### 빈 곳 인식 (Gap Detection)

knowledge_status와 knowledge_lint에서 보고:

```
빈 곳 감지 기준:
  1. 카테고리에 파일이 0~1개인 경우
  2. 검색에서 결과 0건인 쿼리 패턴이 반복되는 경우
  3. _router.md에 카테고리는 있지만 내용이 부족한 경우
  4. 특정 태그로 검색하면 결과가 적은 경우

보고 형태:
  knowledge_gaps: [
    { category: "devops", description: "kubernetes, docker 관련 지식 부족" },
    { category: "research", description: "최근 트렌드 업데이트 필요" }
  ]
```

### LLM 주도 확장

시스템은 "빈 곳이 어디인지" 알려주고, LLM이 주도적으로 채움:

```
LLM → knowledge_status()
시스템: {knowledge_gaps: [{category:"devops", ...}]}

LLM 판단: "devops 지식이 부족하구나. 채워야겠다."
LLM → learn_url("https://kubernetes.io/docs/concepts/overview/")
LLM → learn_fact(category="devops", title="Kubernetes 개요", ...)
LLM → learn_url("https://docs.docker.com/get-started/")
LLM → learn_fact(category="devops", title="Docker 기초", ...)
```

## 5. 복리 (Compound) - Karpathy 핵심 원칙

### 질문의 답 → 위키에 재투입

Karpathy: "좋은 답변은 위키에 새 페이지로 저장될 수 있다."
bluewater: "모든 작업은 두 가지 결과물을 만든다 (답변 + 위키 업데이트)."

```
사용자: "Python과 Go를 비교해줘"
LLM: (knowledge_search로 각각 검색, 답변 생성)
LLM: "Python은 ... Go는 ..."

그리고:
LLM → learn_fact(
  category="programming",
  title="Python vs Go 비교",
  content="... (방금 생성한 비교 분석) ...",
  metadata={source:"query_synthesis", tags:["python","go","comparison"]}
)
```

다음에 같은 질문이 오면, 이미 정리된 비교 페이지가 바로 검색됨.
지식이 복리로 쌓이는 메커니즘.

### 탐색의 복리

```
1일차: "Python 데코레이터" 질문 → 기본 설명 저장
5일차: "데코레이터 실전 패턴" 질문 → 심화 내용 추가
10일차: "데코레이터 성능 영향" 질문 → 성능 분석 추가
  → python-decorators.md가 점점 풍부해짐
  → 처음 만든 페이지가 종합 참고 자료로 성장
```

## Evolution Timeline (예상)

```
Day 1:    빈 위키. 첫 대화에서 몇 가지 사실 학습.
Day 7:    카테고리 3~5개. 파일 20~30개. 기본 구조 형성.
Day 30:   카테고리 10+. 파일 100+. LLM이 DB 테이블 2~3개 생성.
          충돌 감지/해결 시작. 복리 효과 체감.
Day 90:   파일 500+. 크로스 레퍼런스 풍부. 구조 재편 1~2회.
          knowledge_lint 정기 실행. 지식 품질 관리 안정화.
Day 365:  파일 2,000+. 여러 도메인의 종합 지식 베이스.
          LLM이 5~10개 테이블 운영. 자율 확장 활발.
```
