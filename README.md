<div align="center">
  <h1>useful feet stuff</h1>

  <p>
    <a href="./docs/README.md">Documentation</a> •
    <a href="./docs/protocol.md">Pedal USB protocol</a>
  </p>
</div>

Config, macros and a CLI for a GWS Fragpedal Quad.

The pedals hold up to 5 profiles and run one at a time. Each profile gives each of the 4 pedals a macro: a plain-text `.idi` program that sends keys or mouse clicks. This repo holds the whole config as text. `pedals.toml` lists the profiles and the macro each pedal runs, and `macros/` holds the macros.

The `pedals` CLI reads the config from the pedals over USB, shows it, compares it with the repo, and switches the active profile. To change the config, edit `pedals.toml` or a macro, then run `bin/pedals apply`. It compiles the macros, saves a backup of the pedals' flash, and writes the repo's config to the pedals. The pedals need no vendor software.

## Quick start

Install Python 3.12 or later on Windows. The CLI needs no packages. Run it from WSL through `bin/pedals`, which finds that Windows Python, because only Windows reaches the pedals' USB device. Close the vendor app, `IDIConfig.exe`, first. The CLI refuses to run beside it, because both programs read the same USB channel.

```bash
bin/pedals status   # firmware, channel and active profile
bin/pedals show     # every profile and its pedals
bin/pedals diff     # this repo against the pedals
```

After the PC reboots, `status` can print `channel    no answer`. Replug the pedals' USB cable. Then run `status` again.

## Checks

Run the tests in WSL with [uv](https://docs.astral.sh/uv/). They use a fake device, so the pedals can stay unplugged.

```bash
uv run pytest
```

CI runs the same command.

## Layout

- `pedals.toml`: the profiles, and which macro each pedal runs.
- `macros/`: every macro, used or not; `macros/templates/` holds starting points.
- `pedals/`: the CLI, with its tests beside each module.
- `bin/pedals`: runs the CLI under Windows Python from WSL.
- `reference/`: the USB HID key codes and the vendor app's macro list.
- `docs/`: the CLI's exit codes and config format, the macro language, the protocol and the flash image format.

## Documentation

See [docs/](./docs/README.md).
