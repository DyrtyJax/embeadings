# emBEADings

Semantic neighborhoods for Beads—without another taxonomy to maintain.

Read-only semantic neighborhoods and freshness-review batches for
[Beads](https://github.com/gastownhall/beads).

Beads dependencies answer “what blocks this?” Semantic neighborhoods answer a different question:
“what related work might also need review after the project changes?” emBEADings is intended to
find that neighborhood without adding durable labels, changing issue state, or replacing Beads'
dependency graph.

> Status: design and public specification. The CLI is not implemented in this repository yet.

## Intended workflow

```text
live Beads data
      │
      ▼
incremental local embeddings
      │
      ├── nearest active and closed neighbors
      ├── duplicate/echo review candidates
      └── balanced disposable batches
                         │
                         ▼
              human or read-only agents
                         │
                         ▼
                 evidence-backed report
```

The tool discovers a Beads workspace, reads current records through the `bd` CLI, computes embeddings
locally, and emits disposable JSON and Markdown reports. A separate human or coordinator may decide
whether any tracker update is appropriate.

## Proposed commands

```bash
embead neighbors <issue-id>
embead batch [--size 9]
embead sweep [--async]
embead status <run-id>
```

See [the product and technical specification](docs/spec.md) for the proposed contracts, safety
invariants, batch format, architecture, and milestones.

## Principles

- **Read-only means read-only.** The executable will contain no issue mutation commands.
- **Beads remains authoritative.** Read through supported `bd --json` interfaces, never a stale export.
- **Semantics complement structure.** Similarity is advisory; dependencies and lifecycle remain Beads data.
- **Disposable analysis.** Vectors, models, batches, and reports live outside application repositories.
- **Local-first and private.** The default provider sends no issue content to a network service.
- **Agent-neutral.** Core analysis does not depend on Codex, Claude, Cursor, or another runtime.

## Relationship to the ecosystem

The project follows Beads' guidance for standalone integrations and draws inspiration from:

- [Thread](https://github.com/jklenk/thread) for strict read-only analytics and agent-consumable output;
- [Mardi Gras](https://github.com/quietpublish/mardi-gras) for optional agent-runtime adapters;
- [Perles](https://github.com/zjrosen/perles) for keeping structural filtering separate from analysis;
- [BeadBoard](https://github.com/jordanhindo/beadboard) for capability-gated reviewer roles.

It is not a dashboard, issue editor, general memory system, or orchestration framework.

## License

MIT
