# Linear adapter v1

The Linear adapter is a read-only acquisition source for the existing emBEADings analysis core. It
does not synchronize trackers, write labels, update relationships, or treat Linear as a Beads export.

## Authentication and scope

The standalone CLI accepts one credential through the environment:

- `LINEAR_API_KEY` for a personal Linear API key; or
- `LINEAR_ACCESS_TOKEN` for an OAuth access token.

Never put either token in a command argument. Select one team with `--linear-team` or `LINEAR_TEAM`.
The value may be the team's ID, key, or exact name. If an exact name is ambiguous, the adapter fails
closed and asks for an ID or key.

The adapter uses Linear's public GraphQL endpoint. Every operation is checked to begin with `query`;
the HTTP transport rejects mutations before making a network request. GraphQL errors, malformed
payloads, duplicate issue identifiers, invalid pagination, self-relations, and unknown lifecycle or
relation types fail without producing a partial analysis.

## Mapping

| Linear | emBEADings |
| --- | --- |
| issue `identifier` | record ID and report identity |
| `title`, `description` | locally embedded semantic text |
| workflow type `backlog` / `unstarted` | `open` |
| workflow type `started` | `in_progress` |
| workflow type `completed` / `canceled` / `duplicate` | `closed` |
| `priority`, labels, `updatedAt` | matching record metadata |
| parent identifier | `parent_id` |
| `blocks` | directed `blocks` edge |
| `duplicate` | directed `duplicate-of` edge |
| `related`, `similar` | canonical symmetric edge |

Linear's global `issueRelations` query is paged separately from team issues. Endpoints outside the
selected team are counted and omitted. Because the ranking core emits one candidate per unordered
issue pair, the adapter retains one deterministic structural edge per pair, preferring `blocks`, then
`duplicate-of`, `relates-to`, and `similar-to`. This prevents reciprocal API views or multiple relation
types from over-counting the dependency admission funnel.

The v1 record type is `issue`; it does not infer epics from child counts or inject project names into
semantic text. Generated branch suggestions are deliberately ignored.

## Privacy and local code evidence

Issue text travels from Linear to the invoking machine and is embedded by the same pinned local model
used for Beads. emBEADings does not send issue text to an embedding service. Vector and run state remain
in platform user cache/state directories rather than the analyzed repository.

Explicit repository-relative paths may be extracted from issue title and description. Observed edit
evidence comes only from local Git worktrees and diffs. Use `--worktree-map ISSUE_ID=PATH` when a Linear
issue identifier is not present in the worktree branch. Linear's generated branch-name field is not
evidence that a branch or edit exists.

## Known v1 limits

- The CLI credential is separate from OAuth state held by an MCP host.
- Relations are fetched across the visible workspace because Linear's global relation connection has
  no team filter; only selected-team endpoints survive normalization.
- Labels beyond the bounded first 50 on one issue are omitted with a non-sensitive source warning.
- Project, cycle, assignee, and generated branch metadata are not embedded in v1.
- The schema-v1 compatibility field `beads_version` is `null` for Linear; generic consumers should use
  `tracker_name` and `tracker_version`.

Linear documents its GraphQL authentication and Relay-style pagination at
[linear.app/developers/graphql](https://linear.app/developers/graphql) and
[linear.app/developers/pagination](https://linear.app/developers/pagination).
