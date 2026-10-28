# Changelog

## 1.2.0 (2026-10-28)

The first public release.

- `scripts/setup.py`: one command for the Python environment
  (`~/.print3d/venv`), a starter `printer.json` with the slicer's paths when
  one is found, and the self-test.
- `install.py`: copies the skill into the skills folder of 13 agents, or
  any folder, then runs the setup.
- Claude Code plugin and marketplace manifests.
- `slice.py --presets machine|process|filament`: lists the preset names
  that `printer.json` needs.
- `SKILL.md` lists every file of the skill, for agents that copy only the
  files a skill names.
- The author's printer config is no longer shipped.
  `templates/printer.json` is an example with placeholders.

## 1.1.0 (2026-10-28)

- `scripts/shapes.py`: a tested library of build123d shapes, 13 recipes.
- `scripts/compare_views.py`: the fidelity gate. It compares silhouettes
  per view (IoU and width-to-height ratio) and warns about the view order
  and mirrored sides.
- `templates/box_template.py` with `box_reference.jpg`: a box-like figure
  that passes the gate.
- Advice in `SKILL.md` on looking at images in any agent, and a table of
  shape recipes.

## 1.0.0 (2026-10-26)

- The first version:
  - a question round before modelling;
  - reference measuring;
  - model templates;
  - mesh, overhang and colour ray checks;
  - slicing with the user's presets and reading the G-code back;
  - colour 3MF projects;
  - read-only Moonraker queries.
