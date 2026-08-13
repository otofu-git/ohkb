# Web interface concept (not implemented)

Korean: [WEB_UI_kr.md](WEB_UI_kr.md)

## Status

ohkb does **not** ship a web server, browser UI, HTTP API, URL fetcher, or remote MCP transport. The supported product surfaces are the local CLI and MCP over stdio. This document records a possible future interface concept only; it is not a roadmap commitment or an installation option.

## Product idea

A human-facing catalog could let people browse and curate the same Markdown and SQLite FTS5 knowledge base that agents use. It would remain a view over `KnowledgeBase`, not a chat product or a second source of truth.

Possible areas:

- browse the category tree and search results;
- read and edit entries;
- inspect status, lint findings, the generated index, and activity history;
- review immutable local source files.

## Non-goals

- hosting models, chat, prompts, or provider routing;
- storing model credentials;
- replacing CLI or MCP as the agent contract;
- becoming a general note-taking application;
- introducing a remote service into the core package.

## Security gates for any future implementation

A future proposal must be reviewed before code is added. At minimum it must define authentication, request-forgery protection, strict local binding defaults, explicit remote-access policy, path confinement, symlink handling, input and upload size limits, dependency isolation, and security tests. It must call only `KnowledgeBase` and preserve filesystem-first dual-write semantics.

Until those gates are designed and approved, Web remains documentation only.
