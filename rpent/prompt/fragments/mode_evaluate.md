This is a single-attempt evaluation of one task.

- You get exactly one episode. Do not call `reset` and do not restart the
  episode.
- Recovery within the same episode is allowed: reposition, retry a grasp, or
  switch approach. That is still one attempt.
- `finish` only submits your audit. The environment's own success check decides
  the outcome; your call does not mark the task solved.
- A skill or primitive that reports success has reached a subgoal. That is not
  proof the whole task succeeded. Report what the tools showed, and report a
  failure honestly when the task's own check never passed.
- Write the audit before `finish`, then stop immediately.
