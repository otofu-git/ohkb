# ohkb — Vision & Philosophy

Korean: [VISION_kr.md](VISION_kr.md)

## One-line definition

**ohkb** — simple local knowledge base for agents.
A local knowledge backend any LLM agent can attach via CLI or MCP.
Markdown for text, SQLite FTS5 for search. No embeddings. No model calls. Fully open source.

## Problem statement

### Problems with classic RAG

- Embedding models add latency and cost
- Vector DB ops are heavy
- Knowledge becomes opaque numbers
- Every query rediscovers facts from scratch — no compounding
- Semantic match is imperfect

### Limits of common memory systems

- Flat append-only notes with no categories or conflict handling
- Cloud memory APIs (black box, paid)
- Framework-tied agent memory
- Coding-agent-only auto memory

### Core observation

Agent instruction files and skills already work in practice.
What is still scarce is a **generic, hierarchical Markdown + BM25** tool contract that any agent can use without embedding infrastructure.

## Core philosophy (six principles)

1. **ohkb never calls an LLM**
   The agent calls tools and decides. ohkb only stores and retrieves data.
   Any model (Claude, GPT, Llama, Gemini, …) can attach.

2. **Text knowledge = Markdown files**
   Human-readable, git-friendly, editable with any editor.
   Knowledge should compound as a durable artifact.

3. **Index = SQLite FTS5 (fixed schema)**
   BM25 weights: title (10×) > tags (5×) > aliases (3×) > content (1×).
   The LLM chooses tags/aliases at write time — no embeddings required.

4. **No embeddings, no vector DB**
   Zero infra cost, fully local, millisecond search at large scale.

5. **Knowledge compounds**
   Answers and updates go back into the wiki.
   One fact per file for precise edits.

6. **Open source, local-first**
   No external service dependency for stohkbe. Data stays on the machine.

## How ohkb differs

| | Pattern-only wiki workflows | ohkb |
|--|----------------------------|------|
| Form | Prompt / schema document | CLI + MCP tools |
| LLM relation | Agent free-edits a folder | Fixed tool contract; ohkb never calls models |
| Search | External or ad-hoc | Built-in FTS5 BM25 |
| Edit | Manual / free-form | learn, edit, meta, forget, restore, … |
| Categories | Schema-dependent | Nested paths first-class |
| Interface | Agent + local files | CLI + MCP modes (readonly / managed / autonomous) |

| | Cloud memory layers | ohkb |
|--|---------------------|------|
| Stohkbe | Remote API | Local MD + SQLite |
| Embeddings | Usually required | None (BM25 + tags) |
| Transparency | Opaque | Human-readable files |
| Offline | Often no | Yes |
| Git | Hard | Native (plain files) |

## Target users

**Primary:** small teams / solo builders who do not want a vector stack.
**Secondary:** agent builders who need long-term knowledge over MCP.
**Tertiary:** researchers and writers who want agents to accumulate knowledge without embeddings.

## Inspiration

- Compiled, compounding knowledge bases (agent-maintained wiki patterns)
- Structured data rendered as Markdown (SQLite as index, not black box)
- Production lessons on typing, token budgets, entity templates
- Memex-era personal curated stores with associative trails
