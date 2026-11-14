# Space 2 image format

The Fragpedal Quad is a set of 4 USB foot pedals. Its flash memory is split into numbered areas called spaces; [protocol.md](protocol.md) covers how to select and read one. Space 2 holds the profile image: every profile's name and settings, and for each pedal its label, description, macro file name and macro source. Space 3 holds the same macros compiled, as [the runtime image](#the-runtime-image) describes. The `pedals` CLI reads only space 2: the macro source is there, so the CLI never has to decompile space 3. `pedals apply` writes both.

The GWS IDI config app (`IDIConfig.exe`), called the vendor app below, writes this image when it saves. All numbers in the image are little-endian.

## Header

The image starts with an 84-byte (`0x54`) header. The records follow it, and the image ends where the records end. Space 2 holds erased flash (`0xFF`) after the image.

| Offset | Type | Field | Value seen |
| --- | --- | --- | --- |
| `0x00` | u32 | magic | `0x86754232` |
| `0x04` | u32 | version | 1 |
| `0x08` | u32 | profile mask | one bit for each profile: `0x01` with 1 profile, `0x1f` with 5 |
| `0x0C` | u32 | length of the records, in bytes | image size minus `0x54` |
| `0x10` | u32 | number of records | |
| `0x14` | u16 × 5 | offset of each profile's first record, from the image start; 0 for a missing profile | |
| `0x1E` | — | zero up to `0x53` | |

When it reads, the CLI checks only the magic, the version and the length of the records. It rejects an image with another magic or version. It also rejects an image larger than 128 KiB, header included, which is its own limit for space 2.

## Records

Each record is a 6-byte record header, then the record's data:

| Field | Type | Holds |
| --- | --- | --- |
| tag | u8 | the record type, from the tag table |
| a | u8 | the profile number, 1 to 5, on profile and slot records |
| b | u8 | the slot number, 1 to 8, on slot records |
| c | u8 | `0x08` on the slot kind record of a used slot; 0 on every other record |
| len | u16 | the length of the data, in bytes |
| data | len bytes | the value |

A string is cp1252 text that ends in one NUL, and its `len` counts the NUL. Macro source is a string, and keeps its own line endings, CRLF or LF. Other data has no NUL.

Where the tag table marks a field "—", the vendor app leaves it uninitialised, so its value changes from one save to the next. The CLI ignores it.

| Tag | Record | a | b | Data |
| --- | --- | --- | --- | --- |
| `0x01` | owner name | — | — | string |
| `0x02` | serial number | — | — | string |
| `0x03` | profile settings | profile | — | 29 bytes; meaning unknown |
| `0x04` | profile name | profile | — | string |
| `0x05` | slot kind | profile | slot | 1 byte: `0x08` for a used slot, `0x00` for an empty one |
| `0x06` | macro file name | profile | slot | string; empty in an empty slot |
| `0x07` | macro source | profile | slot | string |
| `0x0b` | pedal label | profile | slot | string |
| `0x0c` | pedal description | profile | slot | string; absent when the pedal has none |
| `0x10` | profile background picture | profile | — | string; optional |
| `0x11` | name of the vendor app's file of key aliases | number of the last profile | — | string |
| `0x12` | name of the vendor app's file of macro names | number of the last profile | — | string |
| `0x13` | unknown | number of the last profile | — | 1 byte, seen as 0 |

Profile records carry tags `0x03`, `0x04` and `0x10`. Slot records carry tags `0x05` to `0x0c`. A slot is one pedal position. Every profile has 8 slots, but the Quad has 4 pedals, so slots 5 to 8 only ever hold an empty slot kind and an empty file name.

The CLI keeps tags `0x11` and `0x12` as the `[files]` table of `pedals.toml`. It keeps each record of any other tag outside this table, `0x13` included, as a `[[record]]` entry, and writes it back after the tag `0x12` record.

## Record order

The vendor app writes the records in this order. The CLI reads them in any order.

1. The owner name, then the serial number.
2. For each profile, from profile 1:
   1. its settings, name and background picture;
   2. for each slot from 1 to 8: the slot kind and the macro file name, then, in a used slot only, the label, the description and the macro source.
3. Tags `0x11`, `0x12` and `0x13`, then any record of another tag.

The CLI writes the records in the same order, and writes 0 in each head byte the tag table marks "—". The header's word at `0x08` holds one bit for each profile, from bit 0 for profile 1.

## The runtime image

Space 3 holds the runtime image: the compiled macros of every profile. [pedals/compiler.py](../pedals/compiler.py) builds it, and [docs/language.md](./language.md) gives the bytecode. Each field is a u32, and each offset counts from the image start.

| Offset | Field |
| --- | --- |
| `0x00` | magic, `0xDEAD0BF0` |
| `0x04` | image length, in bytes |
| `0x08`, `0x0C` | 0 |
| `0x10`, `0x14` | offset and length of the thread table: 12 bytes per thread |
| `0x18`, `0x1C` | offset and length of the procedure table: 4 bytes per procedure |
| `0x20`, `0x24`, `0x28` | offset, length and count of the string table |
| `0x2C`, `0x30` | offset and length of the variable inits; the CLI writes none |
| `0x34`, `0x38` | offset and length of the code |
| `0x3C` | number of variables; the CLI writes 0 |
| `0x40`, `0x44` | number of threads, then number of procedures |

The tables and the code follow the header in that order.

- A thread entry is 0, the profile mask (`1 << (profile - 1)`), then the thread's code offset.
- A procedure entry is the procedure's code offset.
- The string table holds a 4-byte length and a 4-byte offset for each string, then the strings, each with one NUL. The length is a u16 that counts the NUL. The offset counts from the start of the string table.
- The code starts at the next multiple of 4 after the string table.

The image length is the string bytes, plus the code, plus 4 × (procedures + 3 × threads + 2 × (strings + 10)). That sum leaves up to 8 bytes after the code. The vendor app never writes those bytes, the padding before the code, or the second u16 of each string length, so their values change from one save to the next. The CLI writes 0 there.

Each macro's procedures come first in the code, then its thread, in pedal order from profile 1. A pedal with no macro has no thread.
