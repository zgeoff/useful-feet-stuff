---
name: pedals
description: Reads, compares, switches and writes the profiles on the owner's GWS Fragpedal Quad foot pedals with the repo's pedals CLI, and writes their macros. Load it to check what the pedals run, change a pedal's macro or label, switch profile, or fix a `no answer` from the pedals.
---

# Pedals

Check and change what the owner's foot pedals run. The pedals store their config in flash, and [`pedals.toml`](../../../pedals.toml) and `macros/` hold the repo's copy of it. [`bin/pedals`](../../../bin/pedals) reads the pedals' copy over USB, compares the two, and writes the repo's copy to the pedals.

You are done when `bin/pedals diff` prints `same` and the change is committed, or when you have the output the owner asked for. Hand back each command you ran with its output, what changed in the repo, and the PR link when you opened one.

Avoid these mistakes:

- running commands while the vendor app, `IDIConfig.exe`, is open: the CLI refuses with exit 6;
- reporting `no answer` as a bug: the pedals need a replug;
- running `pull` over edits you have not committed, which it overwrites;
- running `apply --yes` without the owner's go-ahead;
- sending your own USB messages to the pedals.

## Key rules

- [Run the CLI](#run-the-cli): from WSL; on exit 6, ask the owner to close the vendor app.
- [Fix no answer](#fix-no-answer): ask the owner to replug the pedals.
- [Change a pedal](#change-a-pedal): start from `same`, edit the repo, and `apply` only on the owner's go-ahead.
- [Write a macro](#write-a-macro): copy a template, with `1` to press a key and `0` to release it.

## Run the CLI

Run `bin/pedals <command>` from the repo root in WSL. The script runs the CLI under Windows Python 3.12 or later. Only Windows reaches the pedals' USB device. Run `bin/pedals --help` for the commands, and read [docs/cli.md](../../../docs/cli.md) for the exit codes.

| Command | Use it to | What it does to the pedals |
| --- | --- | --- |
| `status` | check the firmware, the USB channel and the active profile | reads |
| `show [profile]` | list each profile's pedals | reads |
| `diff` | compare the repo with the pedals | reads |
| `pull` | overwrite `pedals.toml`, and each macro a pedal runs, with the pedals' copy | reads |
| `switch <profile>` | change the active profile, by number or exact name | changes the active profile only |
| `apply` | write the repo's config to the pedals | saves a backup, then erases and rewrites the config |
| `restore <folder>` | write a backup to the pedals | saves a backup, then erases and rewrites the config |

- When a command exits 6 with `IDIConfig.exe is running`, ask the owner to close the vendor app, then run it again. Both programs read the same USB channel.
- `switch` needs no go-ahead. The owner can switch back at any time. `pedals.toml` holds no active profile, so `diff` ignores a switch.
- `diff` exits 1 and lists each difference when the repo and the pedals differ. Otherwise it prints `same` and exits 0. After either, it prints an `unused` line for each macro no pedal runs. Leave those files: they are spare macros.

Never send USB messages to the pedals yourself. The CLI erases and writes only the config. The firmware sits in the same flash, and a message you build by hand could overwrite it. [docs/protocol.md](../../../docs/protocol.md) lists every message, to help you read the CLI's code.

## Fix no answer

After some PC reboots, the pedals' USB channel takes messages and never answers. Every command then prints `channel    no answer` and exits 3. The pedals still send their keys.

1. Ask the owner to unplug the pedals' USB cable, wait 5 seconds and plug it back in.
2. Run `bin/pedals status`. Expect: `channel    ok`.

When `status` still prints `no answer`, stop and tell the owner.

## Change a pedal

`apply` erases and rewrites the pedals' config. Get the owner's go-ahead before every `apply` and every `restore`.

1. Run `bin/pedals diff`. Expect: `same`. When it lists a difference, the pedals or the repo changed since the last sync. Show the owner the difference, and ask which side holds the config they want:
   - the pedals: commit your own edits first, so `pull` cannot overwrite them, then run `bin/pedals pull` and commit the result;
   - the repo: go on to step 2.
2. Edit [`pedals.toml`](../../../pedals.toml). [docs/cli.md](../../../docs/cli.md#pedalstoml) gives its format: each `[[profile]]` lists its pedals in order, from pedal 1. Set a pedal's `label`, or set its `macro` to a file name in `macros/`, such as `ReopenTab.idi`.
3. For a new macro, write it as [Write a macro](#write-a-macro) says.
4. Run `bin/pedals diff`, and show the owner its output.
5. On the owner's go-ahead, run `bin/pedals apply --yes`. Expect: a `backup` line, then `wrote`.
6. Run `bin/pedals diff`. Expect: `same`.
7. Commit the change and open a PR. Follow the branch and commit conventions in your instructions for this repo.

When `apply` exits 4, it sent nothing to the pedals. Its output shows a macro file and a line: fix that line, and run `apply` again.

When `apply` exits 5, the write failed, and the pedals may send no keys until a write succeeds. Tell the owner at once, and show them the output. On their go-ahead, run the `bin/pedals restore` command the output ends with. When `restore` fails too, stop, and show the owner both outputs. For where each backup goes, see [docs/cli.md](../../../docs/cli.md#what-apply-and-restore-do).

## Write a macro

- Copy a template from [macros/templates/](../../../macros/templates/), or a macro in `macros/` that does something close, with `cp`. Name the copy after what it does, such as `ReopenTab.idi`. When other pedals run the macro you would change, change a copy, so those pedals keep theirs.
- Edit the copy in place, and keep its line endings. `bin/pedals diff` compares each macro byte for byte, and [`.gitattributes`](../../../.gitattributes) makes Git keep the bytes as they are.
- Keep the copy's `PROCEDURE` and `THREAD` layout, which [docs/language.md](../../../docs/language.md) explains. Use only the statements and builtins that doc lists: `apply` rejects anything else.
- In `KeyActionHid(<modifier>, <key>, <action>)`, pass `1` to press the key and `0` to release it. Press in `ButtonDown` and release in `ButtonUp`, as the templates do.
- Take key codes and modifier bits from [reference/usb_hid_keys.h](../../../reference/usb_hid_keys.h). For two modifiers, add their bits: Ctrl+Shift is `0x03`.

**Reply:** each command you ran and its output, what changed in the repo, and the PR link when you opened one.
