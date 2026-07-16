# Retrieve–verify private regression 03

The private Linear evaluator pinned commit `ea3c0fb` and the installed executable before running the
full protocol. Direct parent/child suppression passed with zero hierarchy pairs in 40 explicit
overlap candidates. Completed-target diversity passed with no closed record admitted more than
twice. Cold and warm candidate IDs and ordering were identical, both repositories remained clean,
and all caches, state, and reports stayed outside the repositories.

The evaluator rated every candidate in the default budget: 27 of 40 were concrete coordination
leads, 13 were useful context, and none were irrelevant. The remaining rating-1 concentration was
mostly hierarchy visible in the legacy default sweep. Whether objective-separated discovery should
replace that default is a compatibility decision tracked separately; it is not folded into this
audit fix.

One audit claim only partially passed. A repeated completed target could report nine qualified, two
admitted, and five target-cap omissions while leaving two candidates unexplained by other governing
caps. Backfill membership was deterministic but the report did not link the omitted and admitted
pairs. The evaluator also correctly characterized diversification as a coverage/relevance trade-off,
not a guarantee that a lower-ranked fallback is more actionable.

The corrected contract now enforces `qualified = admitted + omitted` for every target affected by
the diversity cap. Omissions are mutually attributed to completed-target, one-echo-per-active,
general per-issue, echo-lane, or run limits. `echo_backfills` links target-cap omissions to a later
fallback admitted for the same active record using candidate IDs and scores only. Reports explicitly
state that this proves a coverage substitution, not a relevance improvement.

On the three public evaluator corpora, candidate IDs and ordering were unchanged from the `ea3c0fb`
checkpoint. Ralph TUI had no true target-cap hub after correcting the governing-reason attribution;
opencode-beads produced three conserved hubs and three backfill receipts; Morphir produced one
conserved hub and no backfill. The emBEADings dogfood corpus produced two conserved hubs and one
backfill. Cold and warm candidate, hub, and receipt arrays were identical, and all public repositories
retained clean Git-status fingerprints.

The behavioral release conclusion remains qualified ship. The next private rerun should validate
the conserved hub equations and receipts; it need not re-establish semantic relevance unless
candidate membership changes.
