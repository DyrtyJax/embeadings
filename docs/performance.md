# Performance benchmark

emBEADings includes a generated public benchmark for the warm similarity-analysis path. It contains
no tracker data, private text, or saved vectors. The fixture deterministically creates 1,000 synthetic
records and 256-dimensional normalized vectors, then measures score-matrix construction, candidate
analysis, and deterministic batching separately.

Run it from an editable development installation:

```console
python benchmarks/benchmark_warm.py
```

The benchmark prints versioned JSON with environment metadata, phase medians, candidate and batch
counts, and whether the five-second target was met. Synthetic acquisition and embedding are reported
as fixture preparation rather than included in the warm analysis total. This makes the benchmark
repeatable without pretending that generated records measure `bd` or filesystem cache performance.

## Reference result

On 2026-07-14, an Apple arm64 reference machine running Python 3.14.4 and NumPy 2.5.1 measured the
1,000-record benchmark's exact candidate phase at **2.40 seconds** median over three repeats. The
scope-aware vectorized implementation reduced the same phase to **1.22 seconds** without changing the
candidate fingerprint (about 49%). The contract remains five seconds for the default benchmark.
Results vary with CPU, BLAS, Python, and corpus shape; run the command on the release environment
instead of treating this observation as a universal guarantee.

The benchmark can also isolate an incremental active scope while retaining every closed record as
completed-work evidence:

```console
python benchmarks/benchmark_warm.py --records 8000 --eligible-active 100 --repeats 1
```

On the same reference machine, exact candidate analysis measured 4.93s / 21.99s / 89.27s at
2K / 4K / 8K full-scope records, compared with prior nested-ranking observations of
9.56s / 22.47s / 129.91s. The 8K corpus with 100 eligible active records took 1.24s in candidate
analysis; the complete analysis including full-population deterministic batching took 5.52s. A real
8,143-record Ruff run fell from 101.20s to 30.69s while preserving all 250 semantic candidates and
their order. These results keep ANN behind a measured-need gate: incremental exact review is practical,
while a full 8K sweep remains an occasional calibration operation rather than a weekly default.

Production sweep reports expose `timings_ms` for acquisition, embedding/cache work, similarity
scoring, candidate analysis, and batching. Those fields make a slow Beads adapter or cache visible
without conflating it with semantic scoring.

## Optional provider and storage comparison

The alternative benchmark is intentionally excluded from runtime dependencies. Install it in a
disposable environment and keep model/cache state outside the repository:

```console
python -m pip install -e . fastembed sqlite-vec
python benchmarks/benchmark_alternatives.py --cache-root /external/embead-benchmark
```

It compares the pinned Model2Vec provider with FastEmbed's ONNX-backed
`BAAI/bge-small-en-v1.5` on a fixed public paraphrase/hard-negative set. It separately measures the
current content-addressed JSON cache and sqlite-vec at 1,000 and 5,000 synthetic 256-dimensional
vectors. The output records quality, cold/warm encoding time, storage time, disk size, deterministic
behavior, and package versions. These are engineering signals, not universal model-quality claims.

The current measured decision is documented in
[the embedding and storage alternatives record](decisions/embedding-storage-alternatives.md).

For end-to-end tests in the 2,000–10,000 record range, use the
[large-corpus evaluation protocol](evaluation-large-corpus.md). It intentionally separates a public
GitHub scale surrogate from evidence collected on a native Beads tracker.
