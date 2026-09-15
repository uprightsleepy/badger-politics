# Issue tracker

Use private local Markdown for new planning drafts unless the user specifies another tracker. This default preserves the public repository's rule that raw working drafts stay outside Git. It does not change the project's existing GitHub workflow.

- Feature directory: `.private/tasks/<feature>/`.
- Specification: `spec.md` in that directory.
- Tickets: `issues/NN-<slug>.md`, one file per ticket, numbered from `01`.
- Record triage state with `Status:` using `triage-labels.md`; append discussion under `## Comments`.
- A skill's instruction to publish a new spec or ticket means write these local files unless external publication is authorized.
- For an explicitly supplied external issue, read that source; update it only within the user's authorized task.

## Large planning efforts

For `wayfinder`, keep `map.md` beside `issues/`. Tickets record `Type: research|prototype|grilling|task`, `Status: open|claimed|resolved`, and optional `Blocked by: NN, NN`.

Select the lowest-numbered open ticket whose blockers are resolved, mark it claimed before work, and append the answer under `## Answer` when resolved. Add a summary and ticket link to the map's decisions. These execution states are separate from triage labels.
