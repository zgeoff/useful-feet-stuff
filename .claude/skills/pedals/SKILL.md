---
name: pedals
description: Reads, compares, switches and writes the profiles on the owner's GWS Fragpedal Quad foot pedals with the repo's pedals CLI, and writes their macros. Load it to check what the pedals run, change a pedal's macro or label, switch profile, or fix a pedals USB channel that stops answering.
---

# Pedals

Check and change what the owner's foot pedals run. The pedals store their config in flash, and `pedals.toml` and `macros/` hold a copy of it. [`bin/pedals`](../../../bin/pedals) reads the pedals' copy over USB, compares the two, and writes the repo's copy to the pedals. You are done when `bin/pedals diff` prints `same`, or when you have the output the owner asked for. Hand back each command you ran with its output, and what changed in the repo.

Avoid these mistakes:

- running a command while the vendor app, `IDIConfig.exe`, is open: the CLI refuses, and you lose time looking for a bug;
- reporting `no answer` as a bug, when the pedals need a replug;
- running `pull` over edits you have not committed;
- running `apply --yes` without the owner's go-ahead;
- sending your own USB messages to the pedals.

## Key rules

- [Run the CLI](#run-the-cli): from WSL, after the owner closes the vendor app.
- [Fix a silent channel](#fix-a-silent-channel): ask the owner to replug the pedals.
- [Change a pedal](#change-a-pedal): edit the repo, show the owner the `diff`, and `apply` only on their go-ahead.
- [Write a macro](#write-a-macro): start from a template, with `1` to press a key and `0` to release it.

## Run the CLI

Run `bin/pedals <command>` from the repo root in WSL. The script runs the CLI under Windows Python 3.12 or later. Only Windows reaches the pedals' USB device. Run `bin/pedals --help` for the commands.

| Command | Use it to | What it does to the pedals |
| --- | --- | --- |
| `status` | check the firmware, the USB channel and the active profile | reads |
| `show [profile]` | list each profile's pedals | reads |
| `diff` | compare the repo with the pedals | reads |
| `pull` | overwrite `pedals.toml`, and each macro a pedal runs, with the pedals' copy | reads |
| `switch <profile>` | change the active profile | changes the active profile only |
| `apply` | write the repo's config to the pedals | erases and writes the flash, after a backup |
| `restore <folder>` | write a backup pair back to the pedals | erases and writes the flash, after a backup |

- Ask the owner to close `IDIConfig.exe` before any command. The vendor app and the CLI read the same USB channel.
- `switch` needs no go-ahead. The owner can switch back at any time.
- `diff` exits 1 and lists each difference when the repo and the pedals differ. Otherwise it prints `same` and exits 0. After either, it prints an `unused` line for each macro no pedal runs. Those lines leave the exit code as it is.

Never send USB messages to the pedals yourself. The flash holds the firmware too, and a wrong message can overwrite it. The CLI cannot reach the firmware. [docs/protocol.md](../../../docs/protocol.md) lists every message, to help you read the CLI's code.

## Fix a silent channel

After the PC reboots, the pedals' USB channel can take messages and never answer. Every command then prints `no answer` and exits 3. The pedals still send their keys.

1. Ask the owner to unplug the pedals' USB cable, wait 5 seconds and plug it back in.
2. Run `bin/pedals status`. Expect: `channel    ok`.

When `status` still prints `no answer`, stop and tell the owner.

## Change a pedal

`apply` rewrites the pedals' flash. Get the owner's go-ahead before every `apply` and every `restore`.

1. Edit `pedals.toml`, or a macro in `macros/`, as [Write a macro](#write-a-macro) says.
2. Run `bin/pedals diff`, and show the owner its output.
3. On the owner's go-ahead, run `bin/pedals apply --yes`. Expect: a `backup` line, then `wrote`.
4. Commit the change.

When `apply` exits 4, fix the file and line it names, and run it again. Nothing reached the pedals.

When `apply` exits 5, the write failed. Show the owner the output, and run the `pedals restore` command it prints only on their go-ahead. [docs/cli.md](../../../docs/cli.md) lists every exit code.

When the owner changed the pedals in the vendor app, run `bin/pedals pull` and commit the result.

## Write a macro

- Copy a template from `macros/templates/` or a macro in `macros/`, and keep its `PROCEDURE` and `THREAD` layout.
- In `KeyActionHid(<modifier>, <key>, <action>)`, pass `1` to press the key and `0` to release it.
- Take key codes and modifier bits from [reference/usb_hid_keys.h](../../../reference/usb_hid_keys.h). For two modifiers, add their bits: Ctrl+Shift is `0x03`.
- Keep the file's line endings. `bin/pedals diff` compares each macro byte for byte, so a line-ending change shows as a difference. `.gitattributes` makes Git keep the bytes as they are.
- Use only the statements and builtins in [docs/language.md](../../../docs/language.md). `apply` rejects anything else.

**Reply:** each command you ran and its output, and what changed in the repo.
