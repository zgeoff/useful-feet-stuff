---
name: pedals
description: Reads, compares and switches the profiles on the owner's GWS Fragpedal Quad foot pedals with the repo's pedals CLI, and drafts their macros. Load it to check what the pedals run, change a pedal's macro or label, switch profile, or fix a pedals USB channel that stops answering.
---

# Pedals

Check and change what the owner's foot pedals run. The pedals store their config in flash, and `pedals.toml` and `macros/` hold a copy of it. [`bin/pedals`](../../../bin/pedals) reads the pedals' copy over USB and compares the two. You are done when `bin/pedals diff` prints `same`, or when you have the output the owner asked for. Hand back each command you ran with its output, and what changed in the repo.

Avoid these mistakes:

- running a command while the vendor app, `IDIConfig.exe`, is open: the CLI refuses, and you lose time looking for a bug;
- reporting `no answer` as a bug, when the pedals need a replug;
- running `pull` over edits you have not committed;
- sending your own USB messages to the pedals.

## Key rules

- [Run the CLI](#run-the-cli): from WSL, after the owner closes the vendor app.
- [Fix a silent channel](#fix-a-silent-channel): ask the owner to replug the pedals.
- [Change a pedal](#change-a-pedal): draft the macro, the owner saves it through the vendor app, then you `pull` and check `git diff`.
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

The CLI writes nothing to the pedals. The owner saves each change through `IDIConfig.exe`, and `pull` copies the result into the repo. `pull` names each macro file as the owner named it in the vendor app, and overwrites a file of that name.

1. Draft the macro in `macros/`, as [Write a macro](#write-a-macro) says. Name it after what it does, like the files beside it, and commit it.
2. Send the owner the profile, the pedal number, the macro file and the label.
3. Ask the owner to load that macro on that pedal in `IDIConfig.exe`, set the label, and save to the pedals. Then ask them to close the app.
4. Run `bin/pedals pull`.
5. Run `git diff`. Expect: the new label in `pedals.toml`, and no change to your macro.
6. Commit the result.

When `git diff` shows another change, show it to the owner, and repeat steps 3 to 5. For a change to a label alone, skip step 1.

## Write a macro

- Copy a template from `macros/templates/` or a macro in `macros/`, and keep its `PROCEDURE` and `THREAD` layout.
- In `KeyActionHid(<modifier>, <key>, <action>)`, pass `1` to press the key and `0` to release it.
- Take key codes and modifier bits from [reference/usb_hid_keys.h](../../../reference/usb_hid_keys.h). For two modifiers, add their bits: Ctrl+Shift is `0x03`.
- Keep the file's line endings. `bin/pedals diff` compares each macro byte for byte, so a line-ending change shows as a difference. `.gitattributes` makes Git keep the bytes as they are.

**Reply:** each command you ran and its output, and what changed in the repo.
