---
name: pedals
description: Reads, compares, switches and writes the profiles on the owner's GWS Fragpedal Quad foot pedals with the repo's pedals CLI, and writes their macros. Load it to check what the pedals run, change a pedal's macro or label, switch profile, or fix a `no answer` from the pedals.
---

# Pedals

Check and change what the owner's foot pedals run. The pedals store their config in flash, and [`pedals.toml`](../../../pedals.toml) and `macros/` hold the repo's copy of it. [`bin/pedals`](../../../bin/pedals) reads the pedals' copy over USB, compares the two, and writes the repo's copy to the pedals. You are done when `bin/pedals diff` prints `same`, or when you have the output the owner asked for. Hand back each command you ran with its output, and what changed in the repo.

Avoid these mistakes:

- running a command while the vendor app, `IDIConfig.exe`, is open: the CLI refuses with exit 6, and you lose time looking for a bug;
- reporting `no answer` as a bug, when the pedals need a replug;
- running `pull` over edits you have not committed;
- running `apply --yes` without the owner's go-ahead;
- sending your own USB messages to the pedals.

## Key rules

- [Run the CLI](#run-the-cli): from WSL, after the owner closes the vendor app.
- [Fix no answer](#fix-no-answer): ask the owner to replug the pedals.
- [Change a pedal](#change-a-pedal): edit the repo, show the owner the `diff`, and `apply` only on their go-ahead.
- [Write a macro](#write-a-macro): copy a template, with `1` to press a key and `0` to release it.

## Run the CLI

Run `bin/pedals <command>` from the repo root in WSL. The script runs the CLI under Windows Python 3.12 or later. Only Windows reaches the pedals' USB device. Run `bin/pedals --help` for the commands, and read [docs/cli.md](../../../docs/cli.md) for the exit codes.

| Command | Use it to | What it does to the pedals |
| --- | --- | --- |
| `status` | check the firmware, the USB channel and the active profile | reads |
| `show [profile]` | list each profile's pedals | reads |
| `diff` | compare the repo with the pedals | reads |
| `pull` | overwrite `pedals.toml`, and each macro a pedal runs, with the pedals' copy | reads |
| `switch <profile>` | change the active profile | changes the active profile only |
| `apply` | write the repo's config to the pedals | saves a backup, then erases and rewrites the config |
| `restore <folder>` | write a backup back to the pedals | saves a backup, then erases and rewrites the config |

- Ask the owner to close `IDIConfig.exe` before any command. The vendor app and the CLI read the same USB channel.
- `switch` needs no go-ahead. The owner can switch back at any time. `pedals.toml` holds no active profile, so `diff` ignores a switch.
- `diff` exits 1 and lists each difference when the repo and the pedals differ. Otherwise it prints `same` and exits 0. After either, it prints an `unused` line for each macro no pedal runs. Those lines leave the exit code as it is.

Never send USB messages to the pedals yourself. The CLI erases and writes only the config. The firmware sits in the same flash, and a message you build by hand could overwrite it. [docs/protocol.md](../../../docs/protocol.md) lists every message, to help you read the CLI's code.

## Fix no answer

After the PC reboots, the pedals' USB channel can take messages and never answer. Every command then prints `channel    no answer` and exits 3. The pedals still send their keys.

1. Ask the owner to unplug the pedals' USB cable, wait 5 seconds and plug it back in.
2. Run `bin/pedals status`. Expect: `channel    ok`.

When `status` still prints `no answer`, stop and tell the owner.

## Change a pedal

`apply` erases and rewrites the pedals' config. Get the owner's go-ahead before every `apply` and every `restore`.

1. Commit or set aside any edits you have not committed, then run `bin/pedals diff`. Expect: `same`. When it lists a difference, ask the owner whether the repo or the pedals hold the config they want.
2. Edit [`pedals.toml`](../../../pedals.toml) for a label or for which macro a pedal runs. [docs/cli.md](../../../docs/cli.md#pedalstoml) gives its format: each `[[profile]]` lists its pedals in order, from pedal 1.
3. For a new macro, write it as [Write a macro](#write-a-macro) says, and set the pedal's `macro` to its file name.
4. Run `bin/pedals diff`, and show the owner its output.
5. On the owner's go-ahead, run `bin/pedals apply --yes`. Expect: a `backup` line, then `wrote`.
6. Commit the change on a branch, and open a PR, as the repo's rules say.

When `apply` exits 4, it sent nothing to the pedals. Fix the macro file and line in its output, and run it again.

When `apply` exits 5, the write failed. The pedals send no keys until a write succeeds, so tell the owner at once. Show them the output, and run the `bin/pedals restore` command it prints only on their go-ahead. `apply` saves each backup as `space2.bin` and `space3.bin` in a new folder under `C:\Users\Public\Public Hardware\GWS\pedal-restore\`, named by the time.

When `diff` shows the owner changed the pedals in the vendor app, run `bin/pedals pull` and commit the result.

## Write a macro

- Copy a template from [macros/templates/](../../../macros/templates/) or a macro in `macros/` that does something close. Name the copy after what it does, such as `ReopenTab.idi`. Copying keeps the file's `PROCEDURE` and `THREAD` layout, which [docs/language.md](../../../docs/language.md) explains, and its line endings.
- In `KeyActionHid(<modifier>, <key>, <action>)`, pass `1` to press the key and `0` to release it. Press in the pedal-down procedure and release in the pedal-up one, as the templates do.
- Take key codes and modifier bits from [reference/usb_hid_keys.h](../../../reference/usb_hid_keys.h). For two modifiers, add their bits: Ctrl+Shift is `0x03`.
- Keep the file's line endings. `bin/pedals diff` compares each macro byte for byte, so a line-ending change shows as a difference. [`.gitattributes`](../../../.gitattributes) makes Git keep the bytes as they are.
- Use only the statements and builtins in [docs/language.md](../../../docs/language.md). `apply` rejects anything else.

**Reply:** each command you ran and its output, and what changed in the repo.
