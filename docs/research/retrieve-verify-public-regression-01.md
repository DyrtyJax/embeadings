# Retrieve–verify public regression 01

The first engineering regression compared the stable v0.3 sweep with explicit overlap/echo
objectives and experimental field-aware retrieval on the three existing public evaluator corpora.
All runs used the pinned Potion model, a weekly budget of 20, external artifacts and caches, and the
same local corpus snapshots used by prior evaluations.

| Corpus | Records | Baseline lanes | Experimental lanes | Shared lane memberships | Experimental-only | Warm runtime |
|---|---:|---|---|---:|---:|---:|
| Ralph TUI | 135 | 4 dependency, 12 echo, 4 overlap | 12 echo, 7 overlap | 13 | 6 | 2.22 s |
| opencode-beads | 94 | 16 echo, 4 overlap | 16 echo, 4 overlap | 13 | 7 | 2.14 s |
| Morphir | 208 | 16 echo, 4 overlap | 16 echo, 4 overlap | 20 | 0 | 2.31 s |

The Ralph difference includes the intended removal of known typed relationships from the semantic
novelty budget. A separate structural-objective dogfood run on emBEADings retained seven typed-edge
review candidates without mixing them into overlap or echo capacity.

Field-local channels selected or tied for the best score in all corpora: 11 of 19 Ralph candidates,
20 of 20 opencode candidates, and 20 of 20 Morphir candidates. That does not establish improved
quality. The public hard-negative fixture showed the MaxSim baseline raising one command-vocabulary
false positive from 0.407 to 0.465, still well below the current overlap threshold. Field views are
therefore candidate-generation evidence only and remain experimental pending blinded rating.

Warm reruns produced byte-identical candidate arrays for every corpus. Whole-record and field caches
had zero misses. Pre/post Git-status fingerprints remained the empty SHA-256 digest for all three
repositories. No reports or cache files were created inside an evaluated repository.

The next evaluator should rate the baseline-only and experimental-only pairs blindly, then report:

- actionable precision at the same budget;
- recovery or loss of previously rated-2 pairs;
- vocabulary-only and broad-subsystem false positives;
- whether field provenance identifies a useful local contract or merely a shared phrase;
- whether the separated structural audit is more useful than dependency candidates mixed into the
  discovery queue.

This is an evaluator-ready checkpoint, not a release-quality conclusion.
