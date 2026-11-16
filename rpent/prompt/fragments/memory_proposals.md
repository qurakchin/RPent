This exploration run may propose new memory, but it must not edit the corpus.

Write each proposal as its own Markdown file in this run's memory inbox, with
YAML frontmatter delimited by `---` lines. The frontmatter must parse as YAML:
quote any value containing `: `, and never start an unquoted value with a
quote. The frontmatter `id` identifies the proposal; the file name does not.

- `id` is a bare slug. Do not repeat `scope`, the kind, a `new_` / `global_` /
  `task-family_` prefix, or a trailing `_draft` inside it.
- Required fields: `scope` (`task-family` or `global`) and `confidence`
  (`single-shot`, `probable`, or `verified`); `evidence.cells` must be a
  non-empty list of the cells this observation came from.

Task-family shape:

```yaml
id: <bare slug>
scope: task-family
suite: <suite>
regime: <regime>
task_id: <task id>
task_language: <verbatim task language>
evidence:
  cells: [<cell>]
  attempts: <attempt count>
confidence: single-shot
```

The merge step derives the published task-family id from `suite`, `regime`, and
`task_id`, so the submitted `id` is only a working label for these entries.

Global shape: `id`, `scope: global`, `evidence`, and `confidence`, plus `kind`
(`primitive`, `perception`, `strategy`, `failure`, or `infra`), a non-empty
`title`, and `applies_when`. The merge step publishes the bare `id`.

- Include the observed result, the conditions under which it held, and the
  failure modes ruled out. Phrase the claim as narrowly as the evidence allows,
  and state "observed, cause unknown" rather than inventing a mechanism.
- If an existing entry already covers the observation and remains consistent,
  do not write a near-duplicate. Propose the same `id` with the new cell in
  `evidence.cells`; the merge step accumulates evidence and raises confidence.
- If an observation contradicts an existing entry, write a separate proposal
  that cites both observations and the conditions under which each may hold.
  Never edit or overwrite the published entry.
- Distil only from a success confirmed by the environment or the operator. A
  conclusion drawn only from failures is not promoted: keep it in working notes
  until a success confirms or refutes it.
- Merging is a separate step after the run. Do not copy proposals into the
  corpus yourself, and do not treat an unmerged proposal as fact in this
  session.
