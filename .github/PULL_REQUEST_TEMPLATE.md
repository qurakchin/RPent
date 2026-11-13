## Problem

<!-- What is wrong or missing today? Link the issue when one exists. -->

## Change

<!-- What changed, and why this approach? Keep the summary reviewable. -->

## Contract and migration

<!--
Describe changed interfaces, defaults, schemas, prompts, tool results, or
stored artifacts. State what remains compatible, what is replaced, and how
existing callers or data migrate. Write "None" when the change has no
contract impact.
-->

## Validation

<!--
List what actually ran for each tier, with the command or artifact path and
the observed result. See CONTRIBUTING.md#validation-evidence for the tier
definitions, evidence rules, and status vocabulary.
-->

- CPU:
- Simulation:
- Real robot:

## Limitations

<!--
What did this change not prove? Examples: a single seed or episode, one GPU
model, one robot, no benchmark success rate, or an untested migration path.
Do not present one successful run as a success rate.
-->

## Checklist

- [ ] I reviewed the complete diff.
- [ ] Tests cover the changed behavior, and no failing test was weakened.
- [ ] I updated documentation and both language trees where behavior changed.
- [ ] Validation claims use the status wording in `docs/STYLE_GUIDE.md`.
- [ ] I updated design status lines and implementation mapping where a design phase landed.
