# Security policy

## Reporting a vulnerability

Until a private reporting channel is published, do not include sensitive tracker content in a public
issue. Open a minimal public issue requesting a private contact channel, without reproduction data.

## Security posture

The planned tool is local-first and read-only. Security-sensitive areas include subprocess argument
handling, workspace discovery, model downloads, cache permissions, report redaction, hosted-provider
configuration, and the guarantee that no tracker mutation path exists.
