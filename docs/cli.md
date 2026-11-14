# The pedals CLI

`bin/pedals` runs the CLI from WSL under Windows Python 3.12 or later. Run `bin/pedals --help` for the commands. This doc holds what `--help` leaves out: the exit codes, the config format, and the rules that keep the pedals safe.

## Exit codes

| Exit | Meaning |
| --- | --- |
| 0 | ok, including `apply` and `restore` when the owner answers no |
| 1 | `diff` found a difference |
| 2 | bad argument: an unknown profile, a name two profiles share, a restore folder without a pair |
| 3 | no device: the USB interface is missing, or the channel never answers |
| 4 | bad repo input: a bad `pedals.toml`, a compile error, an image over its size limit |
| 5 | a write failed; the CLI prints the `pedals restore` command |
| 6 | refused: `IDIConfig.exe` runs, or the firmware is old-style |
| 7 | bad device data: a bad image header, a macro in slot 5 to 8, a `pull` conflict |

## pedals.toml

`pedals.toml` and `macros/` hold every space 2 field a person edits. The serial number stays on the device: `apply` reads it from the pedals and writes it back.

```toml
owner = "Your Name Here"            # tag 0x01

[files]                             # optional
aliases = "Windows Aliases.txt"     # tag 0x11
macros = "Windows Macros.txt"       # tag 0x12

[[profile]]                         # in profile order; 1 to 5 profiles
name = "Racing Sim"                 # tag 0x04
image = "track.png"                 # tag 0x10; optional
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

## Writing to the pedals

- `apply` compiles the repo first, and stops with exit 4 on a compile error, before it sends anything.
- `apply` writes nothing when `diff` finds no difference.
- `apply` and `restore` ask before they write. `--yes` skips the question.
- Before the first erase, both save the pair on the device to a new folder in `C:\Users\Public\Public Hardware\GWS\pedal-restore\`, named by the time.
- `apply` reads the config back after the write, and exits 5 when it differs from the repo.
- `restore <folder>` writes a saved `space2.bin` and `space3.bin`. It works when the device holds no readable image.

[protocol.md](./protocol.md#writing-the-flash) gives the write sequence and its checks.
