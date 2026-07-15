# Public code-surface pilot 01: aggregate findings

Evaluation date: 2026-07-15

This report contains aggregate measurements from three public Beads repositories. Raw issue IDs,
titles, descriptions, repository paths, source, reports, and tracker exports were not copied into
emBEADings. The repositories are named only so the corpus shape can be reproduced independently.

## Corpus and coverage

| Repository | Active records | Surface pointers | Records with explicit pointers | Observed worktree surfaces |
|---|---:|---:|---:|---:|
| Morphir | 53 | 59 | 19 | 0 |
| opencode-beads | 36 | 13 | 9 | 0 |
| ralph-tui | 17 | 4 | 4 | 0 |
| **Total** | **106** | **76** | **32** | **0** |

Only 30.2% of active records contained a conservative path or `path::symbol` pointer. Each corpus
had one discovered Git worktree and no worktree associated with an active Bead, so this round tests
explicit task pointers rather than observed agent edits. Collision recall for pointer-free records is
therefore unknown.

## Hub-guard result

The first run used the original exact-file/shared-module policy. It emitted 119 leads, including
all-pairs fan-out around design documents and central implementation files. The default hub guard,
which summarizes explicit-only surfaces referenced by more than five active records, reduced the
queue to 26 leads:

| Repository | Before guard | Default guard | Hub-only pairs omitted |
|---|---:|---:|---:|
| Morphir | 95 | 17 | 78 |
| opencode-beads | 21 | 6 | 15 |
| ralph-tui | 3 | 3 | 0 |
| **Total** | **119** | **26** | **93** |

The retained queue contained 19 exact-file and 7 shared-module leads. All 26 looked worth
investigating when screened from public titles and the narrow shared surface. This was not a blinded
review and did not verify the source-level edit contract, so it is evidence of review usefulness—not
a precision estimate for actual merge conflicts.

## Sensitivity

| Maximum explicit records per non-hub surface | Morphir | opencode-beads | ralph-tui | Total |
|---:|---:|---:|---:|---:|
| 3 | 7 | 0 | 3 | 10 |
| **5 (default)** | **17** | **6** | **3** | **26** |
| 8 | 20 | 21 | 3 | 44 |

Five is the best current default: three suppresses useful narrow coordination leads, while eight
restores most of the central-file fan-out. It remains a corpus-level heuristic and is exposed as
`--max-hub-surface-issues` rather than presented as a universal threshold.

## Safety and determinism

- Tracker export fingerprints and full Git status fingerprints were unchanged in all three repos.
- Reports remained outside the analyzed repositories.
- Repeated report hashes were byte-identical.
- `collisions` did not load an embedding model or require issue-content network activity.

## Decisions and blind spots

1. Keep the default hub limit at five and report suppressed hubs and pair counts rather than silently
   dropping them.
2. Never suppress an exact path observed in an associated active worktree. Observed edits are stronger
   evidence than frequently mentioned task text.
3. Keep pointers and revision provenance in reports; do not copy code snippets or build a source-vector
   index in the MVP.
4. Treat the 26 retained pairs as bounded coordination leads, not predicted conflicts.
5. Use the private pilot to evaluate explicit, observed, and corroborated evidence separately. It must
   include active worktrees or explicit `--worktree-map` associations.
6. Measure recall before adding Git-history, symbol-index, or semantic-code providers. The largest
   current blind spot is absent task-to-code evidence, not ranking among records that already name a
   narrow surface.
