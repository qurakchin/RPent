# Toolkits

Shared tool capabilities live in `components/toolkits/<name>/`. Each toolkit is an
installable component with its own `component.toml`: it owns the implementation,
input contracts, internal primitives, and evaluation fixtures for one capability,
and exposes a small set of tools to the planner.

Toolkits run in the RPent process family. They may depend on core contracts, but
must not import `robots.*` or another toolkit; `python -m tests.tooling.layout` enforces
that boundary. `rpent-install` installs profiles, not individual components: a
profile selects the toolkit with `[components.<name>]`, or another component
that the profile installs requires it.

`geometry/` is the shared localization toolkit: it selects and segments a
target, back-projects the mask, and reports a world-frame estimate, together
with a frozen CPU evaluation corpus. `rpent-install install tool-geometry` installs
it with that corpus. Add another toolkit here only when the capability has an
independent consumer and evaluation corpus; robot-specific behavior belongs
under `robots/<robot>/`.
