This exploration run may propose new memory, but it must not edit the corpus.

- Write each proposal as its own file in this run's memory inbox. One insight
  per file keeps proposals reviewable and mergeable.
- Give every proposal YAML frontmatter with at least: `layer` (task-specific,
  task-family, or global), `task` or `recipe_tag` as the key, and a one-line
  `summary`.
- Include the evidence: what was attempted, the observed result, the parameter
  ranges that worked, and the failure modes that were ruled out.
- Do not overwrite existing entries. A proposal that contradicts memory should
  say so and cite both observations; the merge step decides.
- Merging is a separate step performed after the run. Do not copy proposals
  into the corpus yourself, and do not treat an unmerged proposal as fact in
  this session.
