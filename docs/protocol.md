# Pedal USB protocol

The `pedals` CLI configures the Fragpedal Quad, a set of 4 USB foot pedals made by GWS, with the messages below. GWS ships a Windows config app, `IDIConfig.exe`, called the vendor app here. The facts come from the vendor app's disassembly, and from its traffic, which a script read out of its memory while it ran against pedals with firmware `Sep 26 2020 14:06:10 Ver 1.0.8`.

## Messages

Both the vendor app and the CLI run on Windows and use the Windows HID API.

- The pedals are USB device `vid_1095&pid_0400`. Their config channel is interface 1 (`mi_01`), HID usage page `0xFF55`.
- A message is 64 bytes. Byte 0 is the command, and byte 1 is the number of argument bytes that follow. The rest is zero. A command with no arguments, such as `01`, has 0 in byte 1.
- A program sends a message with `HidD_SetOutputReport`, in a 65-byte buffer that starts with report ID 0. So message byte 0 sits at buffer byte 1.
- A program reads 65-byte input reports with overlapped `ReadFile`, and drops the report ID in front.
- All numbers are little-endian.

The device answers each command with the command byte plus `0x80`, such as `82` for `02`. New-style firmware breaks this rule once: it answers `01` with `91`. The two styles are under [Firmware styles](#firmware-styles).

The device also sends reports that answer no command. A program that waits for an answer skips them:

- `a1 <len> <text>`: debug text, such as `kBHSetFlashSpace 2` after a `0d` command.
- `a0` and `a2` to `a7`: requests for the vendor app to play a sound or show text on screen.

## Commands

The table lists the commands in the order a config session uses them.

| Send | Meaning | Answer |
| --- | --- | --- |
| `01` | get version | `91 <x> <flags:u32> <text>`: byte 1 is not a length here; the version text runs from byte 6 to a NUL |
| `0b` | get active profile | `8b 01 <profile>`; profile numbers start at 1 |
| `0d 01 <space>` | select a flash space | `8d` |
| `02 06 <len:u16> <addr:u32>` | read `len` bytes, 62 at most, from the selected space | `82 <n> <data[n]>` |
| `04 01 <profile>` | switch the active profile | `84` |
| `08` | stop the runtime, the device's macro interpreter | `88` |
| `05 01 <sector>` | erase 64 KiB sector number `<sector>`; the device logs `kBHEraseFlashSector <sector × 0x10000>` | `85` |
| `03 <len+6> <len:u16> <addr:u32> <data>` | write `len` bytes, 56 at most, never across a 256-byte boundary | `83` |
| `09` | start the runtime | `89` |

The CLI sends only `01`, `0b`, `0d`, `02` and `04`. It never stops the runtime, erases or writes.

## Firmware styles

The vendor app tells two firmware styles apart by their answer to `01`:

- New-style firmware answers `91`. Its flash has numbered spaces, which `0d` selects. `Ver 1.0.8` is new-style.
- Old-style firmware answers `81`, and keeps its data at fixed flash addresses.

The CLI supports only new-style firmware. When it gets `81`, it stops before it sends anything else.

## Flash spaces

| Space | Holds | Size |
| --- | --- | --- |
| 2 | the profile image: profile names, pedal labels, macro file names and macro source; [image-format.md](image-format.md) gives its layout | given by its header, 128 KiB at most |
| 3 | the runtime image: the compiled macros of every profile | `0xC000` bytes at most |
| 4 | manufacturing data: serial number and product text | `0x624` bytes |
| 0 | firmware | |
| `0x81` | firmware | |

For a firmware update, the vendor app selects space `0x81` when bit 0 of the `91` flags is set, and space 0 when it is clear. The CLI never selects either.

Space 3 holds the code of every profile, so `04 01 <profile>` switches profile with no flash write.

## Reading the profile image

The vendor app reads the profile image at startup, and the CLI reads it in the same order:

1. Send `01`. Expect: `91`.
2. Send `0b`. Expect: `8b` with the active profile.
3. Send `0d 01 02`. Expect: `8d`.
4. Read 62 bytes, then 22 bytes, from address 0. Expect: `82` for each. Together they are the 84-byte header.
5. Take the record-area length, a u32 at header offset `0x0C`.
6. From address 84, read that many bytes, 62 or fewer at a time. Expect: `82` for each.

## Writing the flash

The vendor app saves a config with this sequence. Each write in steps 5 and 7 is followed by a read of the same bytes, and the vendor app compares the two before the next write.

1. Send `08` to stop the runtime. Expect: `88`.
2. Send `0d 01 02`. Expect: `8d`.
3. Send `05 01 00`. Expect: `85`.
4. Send `05 01 01`. Expect: `85`.
5. Write the profile image to space 2, from address 0. Expect: `83` for each write.
6. Send `0d 01 03`. Expect: `8d`.
7. Write the runtime image to space 3, from address 0. Expect: `83` for each write.
8. Send `09` to start the runtime. Expect: `89`.
9. Send `04 01 <profile>` with the profile that was active before step 1. Expect: `84`.

The sequence erases nothing after it selects space 3, yet after a save space 3 reads back as erased (`0xFF`) past the new runtime image, where the old, longer image was. Which of the two erases clears space 3 is not known: space 2 reads as erased at `0x10000`, so sector 1 is not simply the start of space 3. Repeat the whole sequence to get the same result.

## The silent channel after a reboot

After a PC reboot, the config channel can accept messages and never answer, for the vendor app and the CLI alike. The pedals still work as pedals. Replug the USB cable, and the channel answers again.

## Running the CLI beside the vendor app

Close `IDIConfig.exe` before you run the CLI. Both programs read answers from the same channel, so either one can take the other's answer. The CLI refuses to run while the vendor app runs.
