# Agent integrations

The project routing in `AGENTS.md` uses these user-level Codex installations. Other contributors need their own installations; cloning this project alone does not install them.

| Source | Installed form | Reviewed version |
| --- | --- | --- |
| [Matt Pocock skills](https://github.com/mattpocock/skills) | 25 standalone skills listed in the upstream published plugin manifest, installed with Codex's Skill Installer | `3cca18b368ae95cdbdebbff572ccafa662551015` |
| [Superpowers](https://github.com/obra/superpowers) | Native plugin `superpowers@superpowers-dev` from its upstream GitHub marketplace | `6.3.0` |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | Native plugin `ponytail@ponytail` from its upstream GitHub marketplace | `4.10.0` |

Matt's README currently describes native Codex packaging as planned; standalone skills are its supported Codex form. The installed set excludes upstream miscellaneous and in-progress experiments. Skill references resolve from the session catalog, without hardcoded plugin-cache versions in project instructions.

## Activation and maintenance

Installed standalone skills become available on the next turn. Restart Codex and start a new task to pick up native plugins. Ponytail's README also calls for reviewing and trusting its lifecycle hooks through `/hooks`; project routing can invoke its skills directly without those hooks.

Use a current Codex CLI with the `plugin` command. If a PATH-installed CLI lacks it, use the desktop app's bundled CLI. Register the upstream marketplaces with `codex plugin marketplace add obra/superpowers` and `codex plugin marketplace add DietrichGebert/ponytail`, then install the selectors above with `codex plugin add`. Verify installation and enabled state with `codex plugin list --json`.

Review upstream changes before updating, especially skill names, trigger rules, hooks, and installer instructions. Update this record and routing after verification. Avoid installing the same collection as both standalone skills and a native plugin.
