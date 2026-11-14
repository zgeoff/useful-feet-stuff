# The pedals CLI

Install Python 3.12 or later on Windows, then run the CLI from WSL as `bin/pedals <command>`. The script finds that Windows Python. Only Windows reaches the pedals' USB device. Run `bin/pedals --help` for the commands, and read on for the exit codes, the format of `pedals.toml`, and what `apply` and `restore` do to the pedals.

The CLI manages a GWS Fragpedal Quad, a set of 4 USB foot pedals. The pedals keep their config in flash memory, in numbered areas called spaces:

- Space 2 holds the profile image: profile names, pedal labels and macro source.
- Space 3 holds the runtime image: the same macros, compiled.

[image-format.md](./image-format.md) gives both layouts, and [protocol.md](./protocol.md) the USB messages.

## Exit codes

| Exit | Meaning |
| --- | --- |
| 0 | ok; also when `apply` or `restore` asks and you answer no |
| 1 | `diff` found a difference |
| 2 | bad argument: see [Bad arguments](#bad-arguments) |
| 3 | no answer: Windows finds no pedals, or the pedals never answer; replug them |
| 4 | bad repo input: see [Bad repo input](#bad-repo-input) |
| 5 | a write failed; the CLI prints the `bin/pedals restore` command |
| 6 | refused: the vendor app, `IDIConfig.exe`, is open, or the pedals run firmware older than the CLI supports |
| 7 | bad data: see [Bad data](#bad-data) |

### Bad arguments

- `show` or `switch` got a profile number the pedals lack.
- `show` or `switch` got a profile name that matches no profile, or matches two.
- `restore` got a folder that lacks `space2.bin`, `space3.bin`, or both.

### Bad repo input

- `pedals.toml` is missing, or breaks the format below.
- A macro has a compile error. The CLI prints the macro file and the line.
- The compiled profile image passes 128 KiB, or the runtime image passes `0xC000` bytes.

### Bad data

- The profile image on the pedals is unreadable. `apply` stops here too; `restore` does not need it.
- The pedals hold a macro on a slot above 4.
- `pull` found two pedals that name the same macro file with different source.
- `restore` got a backup file shorter than the length in its header.

## pedals.toml

`pedals.toml` and `macros/` hold every part of the config a person edits. `pull` writes them from the pedals, and `apply` writes the pedals from them.

Each key below maps to one record type, called a tag, in the profile image. `pull` writes the `[[record]]` entries; you rarely write one by hand.

```toml
owner = "Your Name Here"            # tag 0x01

[files]                             # optional
aliases = "Windows Aliases.txt"     # tag 0x11
macros = "Windows Macros.txt"       # tag 0x12

[[profile]]                         # in profile order; 1 to 5 profiles
name = "Racing Sim"                 # tag 0x04
image = "track.png"                 # tag 0x10: the vendor app's background picture; optional
settings = "6464000000000000000f0f0f0000000000000000000000000000000000"  # tag 0x03, 29 bytes in hex

  [[profile.pedal]]                 # in pedal order, from pedal 1, the rightmost; 1 to 4 pedals
  macro = "Horn.idi"                # tag 0x06; the file in macros/ is tag 0x07
  label = "Horn"                    # tag 0x0b
  description = "Sound the horn"    # tag 0x0c; optional

[[record]]                          # a tag the CLI does not model
tag = 0x13
profile = 1                         # the profile number the record carries, from 1
data = "00"
```

The serial number is not in the repo. Before `apply` erases the pedals, it reads their serial number, and it writes that number into the new profile image.

## What apply and restore do

`apply` writes the repo's config to the pedals. `restore <folder>` writes a backup to the pedals, serial number included, and then switches to profile 1.

1. `apply` compiles the macros. On a compile error it exits 4, and sends nothing to the pedals.
2. `apply` compares the repo with the pedals. When they match, it writes nothing.
3. Both commands ask before they write. `--yes` skips the question.
4. Both commands save the pedals' current profile image and runtime image as `space2.bin` and `space3.bin`, in a new folder under `C:\Users\Public\Public Hardware\GWS\pedal-restore\`. The folder name is the time, such as `20260301-093000`. When the pedals' profile image is unreadable, `restore` saves no backup.
5. Both commands erase spaces 2 and 3, and write the profile image and the runtime image they hold.
6. `apply` reads the config back, and exits 5 when it differs from the repo.

Pass `restore` the Windows path of a folder from step 4, in quotes, such as `bin/pedals restore "C:\Users\Public\Public Hardware\GWS\pedal-restore\20260301-093000"`. When a write fails, the CLI prints that command for you. [protocol.md](./protocol.md#writing-the-flash) gives the write sequence and its checks.
