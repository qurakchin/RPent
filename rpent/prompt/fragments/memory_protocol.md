Memory is a read-only corpus for this run. Read it before planning, and never
edit the corpus directly.

- Layers, from most specific to most general:
  - `task-specific/`: one entry per task or recipe, keyed by task or reference
    tag.
  - `task-family/`: patterns shared by a family of related tasks.
  - `global/`: conventions that apply across tasks.
- Start with the entry for the current task or its reference tag, then widen to
  the task family and global layers only if the specific entry is missing or
  clearly does not apply.
- An entry may have a companion recipe file. The recipe gives the command
  sequence; the memory entry gives the reasoning, parameter ranges, and failure
  modes. Read both before adapting a sequence to a new scene.
- Memory is evidence from earlier runs, not ground truth for this scene.
  Re-derive coordinates and verify object identity from the current state.
- Use `list_dir` and `read_text_file` to inspect the corpus. Do not dump whole
  memory layers into the prompt or copy their text into your response.
