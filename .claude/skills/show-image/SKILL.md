---
name: show-image
description: Open a PNG (or any image) from the WSL repo in the Windows default viewer via explorer.exe. Use when the user types /show-image, or asks to show, open, or view a render or image.
---

# Show an image

Open each image in the Windows default viewer. This works from a WSL shell
(`wslpath`) and from Git Bash on Windows (`cygpath`), which is what Claude
Code's Bash tool and `!` commands run in here:

```bash
f=path/to/image.png
if command -v wslpath >/dev/null; then w=$(wslpath -a -w "$f"); else w=$(cygpath -a -w "$f"); fi
explorer.exe "$w"
```

Use `-w` (backslashes). `-m` gives `//wsl.localhost/...`, which explorer.exe
does not understand, so it opens Documents instead of the image.

## Arguments

- One or more paths, relative to the repo root or absolute. Globs are fine
  (`build/case-renders/case-6061-*.png`). Run the command once per file.
- No argument: list the PNGs under `build/product-renders/` and
  `build/case-renders/`, newest first, and ask which to open. Those are the
  render outputs (see `pcb-product-render`).

## Steps

1. Check each file exists first (`ls -l`). If it is missing, say so and
   point at the script that writes it (`export_board_3d.py` then
   `build_product_scene.py` for board renders, `hardware/cad/renders/*.py`
   for case renders). Do not open a folder in its place.
2. Run the command above for each file.
3. explorer.exe exits with code 1 even when it works. Do not treat that as a
   failure or retry.

## Shell notes

Git Bash has no `wslpath`; that is why the command picks `cygpath` there.
Do not wrap it in `wsl -- bash -lc '...'`: the outer shell expands
`$(...)` first. From PowerShell, skip the conversion and pass the UNC path:
`ii \\wsl.localhost\Ubuntu-24.04\home\zachr\repos\pixel-snap-voice\<path>`.

Report which files were opened. Do not describe image contents unless the
user asks; if they do, Read the PNG to look at it.
