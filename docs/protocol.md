# Pedal USB protocol

The `pedals` CLI configures the Fragpedal Quad, a set of 4 USB foot pedals made by GWS, with the messages below. GWS ships a Windows config app, `IDIConfig.exe`, called the vendor app here. The facts come from a disassembly of the vendor app. They also come from the vendor app's traffic with pedals on firmware `Sep 26 2020 14:06:10 Ver 1.0.8`. A script read that traffic out of the vendor app's memory.

## Messages

Both the vendor app and the CLI run on Windows and use the Windows HID API.

- The pedals are USB device `vid_1095&pid_0400`. Their config channel is interface 1 (`mi_01`), HID usage page `0xFF55`.
- A message is 64 bytes. Byte 0 is the command, and byte 1 is the number of argument bytes that follow. The rest is zero. A command with no arguments, such as `01`, has 0 in byte 1.
- A program sends a message with `HidD_SetOutputReport`, in a 65-byte buffer that starts with report ID 0. So message byte 0 sits at buffer byte 1.
- A program reads 65-byte input reports with overlapped `ReadFile`, and drops the report ID in front.
- All numbers are little-endian.

The device answers each command with the command byte plus `0x80`, such as `82` for `02`. New-style firmware breaks this rule once: it answers `01` with `91`. The two styles are under [Firmware styles](#firmware-styles).

The device also sends reports that answer no command. A program that waits for an answer skips them:

- `a1 <len> <text>`: debug text, such as `kBHSetFlashSpace 2` after a `0d` command. The firmware also sends `<count> SW <pedal>` when a pedal goes down, and `<count> SW` when it comes back up. When a press brings no `SW` text, the firmware never saw it, and the fault is in the pedal, its cable or its socket.
- `a0` and `a2` to `a7`: requests for the vendor app to play a sound or show text on screen.

## Commands

The table lists the commands in the order the vendor app first sends them.

| Send | Meaning | Answer |
| --- | --- | --- |
| `01` | get version | `91 <unknown> <flags:u32> <text>`: byte 1 is not a length here; the version text runs from byte 6 to a NUL |
| `0b` | get active profile | `8b 01 <profile>`; profile numbers start at 1 |
| `0d 01 <space>` | select a flash space, as [Flash spaces](#flash-spaces) lists | `8d` |
| `02 06 <len:u16> <addr:u32>` | read `len` bytes, 62 at most, from the selected space | `82 <n> <data[n]>` |
| `04 01 <profile>` | switch the active profile | `84` |
| `08` | stop the runtime, the device's macro interpreter | `88` |
| `05 01 <sector>` | erase 64 KiB sector number `<sector>`; the device logs `kBHEraseFlashSector <sector × 0x10000>` | `85` |
| `03 <len+6> <len:u16> <addr:u32> <data>` | write `len` bytes, 56 at most, never across a 256-byte page | `83 01 <status>`; status 0 is ok |
| `09` | start the runtime | `89` |

The CLI's `status`, `show`, `pull`, `diff` and `switch` commands send only `01`, `0b`, `0d`, `02` and `04`. Only its `apply` and `restore` commands send `08`, `05`, `03` and `09`, as [Writing the flash](#writing-the-flash) says. The CLI never selects space 0 or `0x81`, which hold the firmware.

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

For a firmware update, the vendor app selects space `0x81` when bit 0 of the flags in the answer to `01` is set, and space 0 when it is clear.

Space 3 holds the code of every profile, so `04 01 <profile>` switches profile with no flash write.

## Reading the profile image

The vendor app reads the profile image at startup, and the CLI reads it in the same order:

1. Send `01`. Expect: `91`.
2. Send `0b`. Expect: `8b` with the active profile.
3. Send `0d 01 02`. Expect: `8d`.
4. Read 62 bytes from address 0, then 22 bytes from address 62. Expect: `82` for each. Together they are the 84-byte header.
5. Take the length of the records, a u32 at header offset `0x0C`, as [image-format.md](image-format.md#profile-image-header) gives it.
6. From address 84, read that many bytes, 62 or fewer at a time. Expect: `82` for each.

## Writing the flash

The CLI's `apply` and `restore` commands write a new profile image and a new runtime image. `apply` builds them from the repo, and `restore` takes them from a backup folder. Both use the vendor app's sequence, steps 2 to 5 and 7 to 10, and add the backup in step 1 and the blank check in step 6.

1. Read the profile image in space 2 and the runtime image in space 3, each to the length its own header gives, and save both to a backup folder. When the profile image is unreadable, `restore` goes on with no backup.
2. Send `08` to stop the runtime. Expect: `88`.
3. Send `0d 01 02`. Expect: `8d`.
4. Send `05 01 00`. Expect: `85`, after about 0.7 s.
5. Send `05 01 01`. Expect: `85`.
6. Read space 2, then select and read space 3, each to the longer of its old and new image. Expect: `0xFF` in every byte.
7. Send `0d 01 02`, and write the new profile image from address 0. Expect: `83 01 00` for each write.
8. Send `0d 01 03`, and write the new runtime image from address 0. Expect: `83 01 00` for each write.
9. Send `09` to start the runtime. Expect: `89`.
10. Send `04 01 <profile>`, then send `0b`. Expect: `8b 01 <profile>`. `apply` sends the profile that was active before step 2, and `restore` sends profile 1.

In steps 7 and 8, each page of 256 bytes takes 4 writes of 56 bytes and 1 of 32. Like the vendor app, the CLI reads back each write. When the bytes differ, it writes them again, for at most 3 writes in all.

The first `04` after `09` gets no `84`: the pedals send only the debug text `kBHChangeProfile <profile>`. The vendor app sends `04` there and ignores the missing answer, so the CLI checks the switch with `0b`.

Which erase clears space 3 is not known, but after steps 4 and 5, space 3 reads as `0xFF`.

### When a step fails

Each failure exits 5, and the CLI prints the `pedals restore` command for the backup from step 1.

- **Step 6 finds space 2 not blank:** the CLI writes nothing, and the runtime stays stopped.
- **Step 6 finds space 3 not blank:** the old runtime image is still in space 3. The CLI writes the old profile image back to space 2, so the two images match again, and sends `09`. The pedals run the old config.
- **Step 10 fails:** the pedals run the new config, on whichever profile they show.
- **A write reads back wrong 3 times, answers a status other than 0, or gets no answer:** the CLI stops. The runtime stays stopped, so the pedals send no keys until a restore or another `apply` succeeds.

## The silent channel after a reboot

After some PC reboots, the config channel accepts messages and never answers, for the vendor app and the CLI alike. The CLI then waits 2 seconds, prints `channel    no answer`, and exits 3. The pedals still work as pedals. Replug the USB cable, and the channel answers again.

## Running the CLI beside the vendor app

Close `IDIConfig.exe` before you run the CLI. Both programs read answers from the same channel, so either one can take the other's answer. The CLI refuses to run while the vendor app runs.
