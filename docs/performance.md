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

On 2026-07-14, an Apple arm64 reference machine running Python 3.14.4 and NumPy 2.5.1 completed the
1,000-record benchmark in **under one second** median analysis time over three repeats. The contract is
five seconds, leaving headroom for slower supported machines. Results vary with CPU, BLAS, Python, and
corpus shape; run the command on the release environment instead of treating this observation as a
universal guarantee.

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
