# Brand assets

These restrained, repository-native assets use no external images or font files:

- `embeadings-mark.svg` — the compact project mark;
- `embeadings-social-card.svg` — editable 1280×640 social-preview source;
- `embeadings-social-card.png` — rendered social-preview upload; and
- `synthetic-collision-evidence.svg` — a synthetic, terminal-style evidence panel for the project
  README.

The mark shows two work paths converging on a shared code surface. The amber surface is a prompt to
coordinate, not a claim that the work necessarily conflicts.

To reproduce the PNG with librsvg:

```bash
rsvg-convert -w 1280 -h 640 \
  assets/brand/embeadings-social-card.svg \
  -o assets/brand/embeadings-social-card.png
```

Keep examples synthetic. Do not place tracker text, repository paths, worktree names, or evaluation
data from a private project in a public brand asset.
