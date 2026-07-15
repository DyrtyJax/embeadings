# Private code-surface pilot 02: aggregate findings

Evaluation date: 2026-07-15

This report contains only aggregate measurements supplied by the repository owner. No issue IDs,
titles, descriptions, labels, repository paths, symbols, snippets, branch names, worktree locations,
raw reports, mappings, fingerprints, or tracker exports were copied into emBEADings.

## Verdict

The tested 0.2.0 commit is a no-go for a public tag. Read-only safety, deterministic output,
exact-file handling, and hub suppression passed. Two product-quality blockers remain:

1. Repository revision provenance came from a stale tracker-owner checkout rather than the worktree
   from which the command was invoked.
2. Only 1 of 22 explicit-only shared-module leads was useful. Broad directory co-ownership is not a
   sufficiently precise primary collision signal.

## Corpus and surface coverage

- 889 live tracker records, including 232 active records.
- 211 active non-epic records evaluated.
- 9 Git worktrees discovered and 1 explicitly associated; none were associated automatically.
- 68 records had explicit-only surfaces, 1 had explicit plus observed surfaces, and 142 had no
  surface evidence. No record had observed-only evidence.
- 124 explicit and 7 observed pointers were extracted.

Because only one record had observed evidence, this round could not substantively evaluate
observed-only or corroborated pair ranking.

## Retained lead quality

All 43 retained leads were explicit-only:

| Evidence kind | Likely collision | Useful coordination | Misleading | Useful share |
|---|---:|---:|---:|---:|
| Exact file | 5 | 9 | 7 | 66.7% |
| Shared module | 0 | 1 | 21 | 4.5% |
| **Total** | **5** | **10** | **28** | **34.9%** |

Exact-file evidence is viable as a review signal. Explicit-only shared-module evidence overwhelms it
with broad directory ownership, documentation references, governance/planning artifacts, and central
files mentioned for inspection rather than modification.

## Hub behavior and sensitivity

At the default limit of five, three hubs were summarized, 43 leads were retained, and 187 pairs were
omitted. A deterministic audit of 20 omitted pairs rated 8 useful and 12 misleading; none involved an
observed active edit. No observed exact-file pair was suppressed.

| Hub limit | Retained | Exact file | Shared module | Hubs | Omitted |
|---:|---:|---:|---:|---:|---:|
| 3 | 18 | 12 | 6 | 6 | 212 |
| **5** | **43** | **21** | **22** | **3** | **187** |
| 8 | 71 | 49 | 22 | 2 | 159 |

The default limit remains defensible after shared-module precision is corrected. A limit of three
hides useful path-level coordination, while eight substantially expands exact-file review.

## Safety, determinism, and performance

- Default and exact-repeat outputs were byte-identical.
- Default runtime was 3.66 seconds and the exact repeat was 2.50 seconds.
- No embedding model loaded; no cache or state files were created.
- Tracker, invoking Git status, invoking repository contents, tracker-owner checkout, and emBEADings
  remained unchanged.
- No repository files were created, and private temporary artifacts were removed.

## Decisions

1. Resolve repository and base provenance from the invoking worktree when it shares the tracker
   repository; warn and fall back safely for unrelated or non-Git invocation contexts.
2. Remove explicit-only shared-module pairs from the primary collision queue and expose a
   deterministic omission count. Retain observed and corroborated module evidence.
3. Keep the default hub limit at five and preserve the observed exact-file exemption.
4. Repeat the private gate with at least two associated active worktrees before creating a public
   0.2.0 tag.
5. Do not begin the Linear transfer probe or missing-pointer provider experiment until the corrected
   private gate passes.
