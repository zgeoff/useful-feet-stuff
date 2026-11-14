# The pedals CLI

The `pedals` CLI manages a GWS Fragpedal Quad, a set of 4 USB foot pedals. Run it from WSL as `bin/pedals <command>`. The script runs the CLI under Python 3.12 or later installed on Windows, because only Windows reaches the pedals' USB device. Run `bin/pedals --help` for the commands. This doc gives the exit codes, the format of `pedals.toml`, and what `apply` and `restore` do to the pedals.

The pedals keep their config in flash memory, in numbered areas called spaces. Space 2 holds the profiles: names, labels and macro source. Space 3 holds the same macros compiled. [protocol.md](./protocol.md) covers the spaces and the USB messages.

## Exit codes

| Exit | Meaning |
| --- | --- |
| 0 | ok; also when `apply` or `restore` asks and you answer no |
| 1 | `diff` found a difference |
| 2 | bad argument: an unknown profile, a name two profiles share, a restore folder without `space2.bin` and `space3.bin` |
| 3 | no device: Windows finds no pedals, or the pedals never answer; replug them |
| 4 | bad repo input: a bad `pedals.toml`, a compile error, or a compiled config larger than the pedals hold |
| 5 | a write failed; the CLI prints the `pedals restore` command |
| 6 | refused: the vendor app, `IDIConfig.exe`, is open, or the pedals run firmware older than the CLI supports |
| 7 | bad data on the pedals: an unreadable space 2, a macro on a pedal number above 4, or two pedals with one macro file name and different source |

## pedals.toml

`pedals.toml` and `macros/` hold every part of the config a person edits. `pull` writes them from the pedals, and `apply` writes the pedals from them. The pedals' serial number is not in the repo: `apply` reads it from the pedals before it erases them, and writes it back.

```toml
owner = "Your Name Here"            # tag 0x01

[files]                             # optional
aliases = "Windows Aliases.txt"     # tag 0x11
macros = "Windows Macros.txt"       # tag 0x12

[[profile]]                         # in profile order; 1 to 5 profiles
name = "Racing Sim"                 # tag 0x04
image = "track.png"                 # tag 0x10: the vendor app's background picture; optional
settings = "6464000000000000000f0f0f0000000000000000000000000000000000"  # tag 0x03, 29 bytes in hex

  [[profile.pedal]]                 # in pedal order; 1 to 4 pedals
  macro = "Horn.idi"                # tag 0x06; the file in macros/ is tag 0x07
  label = "Horn"                    # tag 0x0b
  description = "Sound the horn"    # tag 0x0c; optional

[[record]]                          # each record of a tag the CLI does not model
tag = 0x13
profile = 1                         # the record's a byte
data = "00"
```

Each tag is a record type in space 2, as [image-format.md](./image-format.md) lists.

## What apply and restore do

`apply` writes the repo's config to the pedals. `restore <folder>` writes a backup back to the pedals.

1. `apply` compiles the macros. On a compile error it stops with exit 4, and sends nothing to the pedals.
2. `apply` compares the repo with the pedals. When they match, it writes nothing.
3. Both commands ask before they write. `--yes` skips the question.
4. Both commands save the pedals' current space 2 and space 3 as `space2.bin` and `space3.bin`, in a new folder under `C:\Users\Public\Public Hardware\GWS\pedal-restore\`. The folder name is the time, such as `20260301-093000`.
5. Both commands erase spaces 2 and 3 and write the new images.
6. `apply` reads the config back, and exits 5 when it differs from the repo.

Pass `restore` the folder from step 4. `restore` still writes when space 2 on the pedals is unreadable, such as after a failed write. [protocol.md](./protocol.md#writing-the-flash) gives the write sequence and its checks.
