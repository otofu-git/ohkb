# Research Summary

Korean: [RESEARCH_kr.md](RESEARCH_kr.md)

Survey notes that informed ohkb’s design. Not a product promise.

## Takeaways

- Most large “memory” and RAG stacks depend on embeddings and/or cloud APIs.
- There is demand for **local, inspectable, agent-operated knowledge** without vector infra.
- Prompt-only wiki patterns prove the workflow; ohkb freezes the **tool contract** (search, dual-write, archive, MCP modes) without calling models.

## Positioning vs common alternatives

| Class | Typical trait | ohkb |
|-------|---------------|------|
| Vector RAG platforms | Embeddings required | No embeddings |
| Cloud memory APIs | Remote black box | Local Markdown + SQLite |
| Flat agent notes | Single file append | Hierarchical atomic entries |
| Compile-heavy wiki tools | System calls LLMs | Agent calls ohkb tools only |

## Design implications

1. Tags/aliases at write time replace embedding quality work.
2. Files remain human-auditable and git-friendly.
3. FTS5 BM25 is enough for an agent-driven, well-tagged corpus.
4. MCP modes (readonly / managed / autonomous) matter for real deployments.
