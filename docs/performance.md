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
