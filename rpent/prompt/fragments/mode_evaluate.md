This is a single-attempt evaluation of one task.

- You get exactly one scored episode. Do not restart it. On a robot whose
  operator protocol requires a scene-reset request before motion, follow that
  protocol; it does not start a second attempt.
- Recovery within the same episode is allowed: reposition, retry a grasp, or
  switch approach. That is still one attempt.
- `finish` only submits your audit. The run's authoritative verdict decides the
  outcome: the environment's own success check, or the operator verdict on
  hardware that requires one. Your call does not mark the task solved.
- A skill or primitive that reports success has reached a subgoal. That is not
  proof the whole task succeeded. Report what the tools showed, and report a
  failure honestly when the authoritative verdict never passed.
- Write the audit before `finish`, then stop immediately.
