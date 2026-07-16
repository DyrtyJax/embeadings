# Retrieve–verify research synthesis

Research reviewed through July 15, 2026 changed the model-upgrade recommendation for emBEADings.
The useful lesson from image retrieval is not to replace the current embedding with one larger
universal vector. Published systems repeatedly retrieve broadly with compact global signals and then
verify a bounded shortlist with local, pair-specific evidence.

Google documents image understanding as a combination of visual content, surrounding page context,
captions, filenames, alt text, and structured metadata. DELG similarly combines global retrieval with
attentive local descriptors. ScaNN accelerates approximate vector search but does not define relevance.
Those patterns map to whole-issue semantics for recall; field-local intent, tracker structure, and
code surfaces for verification; and approximate indexing only after measured scale requires it.

Recent context research reinforces the same direction:

- Agentic-R distinguishes semantic relevance from downstream task utility.
- CatRAG reports query-independent graph traversal drifting into high-degree hubs.
- QueryLink aligns the information need with coherent, multi-grained memory units.
- Stable-RAG reports sensitivity to the ordering of the same retrieved context.
- ReasoningBank distills structured lessons from both successful and failed trajectories.

For emBEADings, the information need must therefore be explicit: edit collision, active-active scope
overlap, active-closed completed-work echo, or structural audit. These objectives need separate
populations, evidence tiers, budgets, and metrics. Known typed edges remain authoritative context but
should consume novelty budget only in structural-audit mode.

The resulting staged architecture is:

1. Freeze evaluator positives and hard negatives.
2. Union independently attributable whole-record, field-local, sparse, structural, and code-surface
   candidate channels.
3. Preserve channel ranks and provenance rather than collapsing everything into an unexplained score.
4. Verify only a bounded pool using a symmetric, task-specific classifier with abstention.
5. Cluster duplicate echoes, summarize hubs, and diversify the final review queue.
6. Learn first from explicit local reason-coded dispositions, never unreviewed results or clicks.

Off-the-shelf GTE and Qwen rerankers remain useful shadow baselines, but their query-to-document
training objective is not the symmetric question emBEADings must answer: whether two work items may
change the same behavior, contract, or implementation boundary. Model selection therefore follows
the public and four-corpus evaluator gates rather than generic retrieval leaderboards.

Primary sources:

- [Google Images documentation](https://developers.google.com/search/docs/appearance/google-images)
- [DELG: local and global image features](https://research.google/pubs/unifying-deep-local-and-global-features-for-image-search/)
- [ScaNN](https://research.google/blog/announcing-scann-efficient-vector-similarity-search/)
- [Agentic-R](https://aclanthology.org/2026.findings-acl.785/)
- [CatRAG](https://aclanthology.org/2026.findings-acl.290/)
- [QueryLink](https://aclanthology.org/2026.findings-acl.765/)
- [Stable-RAG](https://aclanthology.org/2026.acl-long.1188/)
- [ReasoningBank](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)
