# Brand assets

These restrained, repository-native assets use no external images or font files:

- `embeadings-mark.svg` — the compact project mark;
- `embeadings-social-card.svg` — editable 1280×640 social-preview source;
- `embeadings-social-card.png` — rendered social-preview upload; and
- `synthetic-collision-evidence.svg` — a synthetic, terminal-style evidence panel for the project
  README.

The light mark shows two internally bonded but mutually unlinked epic molecules extending toward a
shared near-touch point. Solid bonds represent known structure inside each epic; the open gap preserves
uncertainty; and the amber point is a prompt to review a possible collision, not a verdict that the work
conflicts. The gesture is intentionally abstract and echoes the near-touch composition of Michelangelo's
*The Creation of Adam* without depicting hands or reproducing the painting.

To reproduce the PNG with librsvg:

```bash
rsvg-convert -w 1280 -h 640 \
  assets/brand/embeadings-social-card.svg \
  -o assets/brand/embeadings-social-card.png
```

Keep examples synthetic. Do not place tracker text, repository paths, worktree names, or evaluation
data from a private project in a public brand asset.
