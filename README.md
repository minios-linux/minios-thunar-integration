# MiniOS Thunar Integration

## Overview

Thin XFCE/Thunar integration for MiniOS module tools.

The package owns two user-facing helpers:

- `minios-thunar-actions` provides GTK dialogs for create/extract and runtime actions while delegating all module work to `dir2sb`, `sb2dir`, and `sb`.
- `minios-thunar-uca-sync` idempotently synchronizes only the fixed MiniOS actions inside the user's `~/.config/Thunar/uca.xml`.

It does not wrap `/usr/bin/thunar`, replace the complete UCA file, implement SquashFS or AUFS operations, or register a competing module MIME type. `application/x-sb` remains owned by `minios-tools` and its icon name is `application-x-sb`.

The generated UCA XML intentionally uses the subset understood by Thunar 1.6 (Ubuntu 18.04) and remains valid on current Thunar releases. Runtime actions are added only when `findmnt -rn --mountpoint / -o FSTYPE` reports `aufs`. The frontend repeats the AUFS check immediately before `sb activate` or `sb deactivate`.

Create and extract operations use the machine-readable backends directly:

    /usr/bin/dir2sb --json -- SOURCE TARGET.sb
    /usr/bin/sb2dir --json -- SOURCE.sb TARGET_DIRECTORY

The GTK progress window reports backend phases using an indeterminate activity indicator because the current JSON protocol does not provide a real numeric completion percentage.

## License

Distributed under the GNU General Public License v2 or later.
