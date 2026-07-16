# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.4.x | Yes |
| Earlier technical previews | No |

Upgrade to the newest published technical preview before reporting a defect when practical.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting flow when the **Report a vulnerability** button is
available on the repository's Security page. Do not include sensitive tracker content, credentials,
repository paths, private issue IDs, raw reports, or reproduction archives in a public issue.

If private reporting is unavailable, open a minimal public issue requesting a private contact channel.
Include only the affected emBEADings version and a high-level component name. A maintainer will arrange
a private exchange before requesting reproduction details.

## Security posture

emBEADings is local-first, read-only, and advisory. Tracker adapters contain no mutation operations.
The default model embeds issue text locally, although its artifacts may be downloaded before issue
loading. Linear mode necessarily queries Linear for the selected team's data. Models, vectors, and
reports are stored outside the analyzed repository by default.

Security-sensitive areas include subprocess argument handling, tracker and worktree discovery, model
downloads, Linear credential handling, cache permissions, report redaction, repository provenance,
plugin boundaries, and the guarantee that no tracker mutation path exists. A read-only guarantee does
not make report contents safe to publish: treat all outputs as potentially sensitive project data.
