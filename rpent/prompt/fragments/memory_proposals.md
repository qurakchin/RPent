This exploration run may propose new memory, but it must not edit the corpus.

- Write each proposal as its own Markdown file in this run's memory inbox, with
  YAML frontmatter delimited by `---` lines. The frontmatter must parse as YAML:
  quote any value containing `: `, and never start an unquoted value with a
  quote.
- `id` is a bare slug. Do not repeat `scope`, the kind, or a `new_` /
  `task-family_` prefix inside it.
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

Global shape: `id`, `scope: global`, `evidence`, and `confidence`, plus `kind`
(`primitive`, `perception`, `strategy`, `failure`, or `infra`), a non-empty
`title`, and `applies_when`.

- Include the observed result, the conditions under which it held, and the
  failure modes ruled out. Phrase the claim as narrowly as the evidence allows,
  and state "observed, cause unknown" rather than inventing a mechanism.
- Do not overwrite existing entries. A proposal that contradicts memory should
  cite both observations; the merge step decides.
- Merging is a separate step after the run. Do not copy proposals into the
  corpus yourself, and do not treat an unmerged proposal as fact in this
  session.
