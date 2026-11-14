# Flash image formats

The Fragpedal Quad keeps its config in two flash areas, called spaces, which [protocol.md](protocol.md) covers. The vendor app, `IDIConfig.exe`, writes both when it saves, and `pedals apply` writes the same layout. Every number in both images is little-endian.

- Space 2 holds the profile image: for each profile, its name and settings, and for each pedal its label, description, macro file name and macro source.
- Space 3 holds the runtime image: every pedal's macro, compiled.

The CLI reads only the profile image, which holds the macro source. It keeps the parts a person edits as text in `pedals.toml`, which [cli.md](cli.md#pedalstoml) describes.

## The profile image (space 2)

### Profile image header

The profile image starts with an 84-byte (`0x54`) header. The records follow it, and the image ends where the records end. Space 2 holds erased flash (`0xFF`) after the image.

| Offset | Type | Field | Value |
| --- | --- | --- | --- |
| `0x00` | u32 | magic | `0x86754232` |
| `0x04` | u32 | version | 1 |
| `0x08` | u32 | profile mask | one bit for each profile, from bit 0 for profile 1 |
| `0x0C` | u32 | length of the records, in bytes | image size minus `0x54` |
| `0x10` | u32 | number of records | |
| `0x14` | u16 × 5 | offset of each profile's first record, from the image start | 0 for a missing profile |
| `0x1E` | — | zero up to `0x53` | |

The CLI fills in every field of this header when it writes. When it reads, it uses only the magic, the version and the length of the records. It rejects an image with another magic or version, or larger than 128 KiB with the header. Before each write, the CLI erases 2 flash sectors of 64 KiB, so 128 KiB is the most it can write.

### Records

Each record is a 6-byte record header, then the record's data. A profile record belongs to one profile. A slot record belongs to one slot of a profile. Every profile has 8 slots, numbered from 1. The Quad has 4 pedals, which use slots 1 to 4. Slots 5 to 8 hold only an empty slot kind and an empty file name.

| Field | Type | Holds |
| --- | --- | --- |
| tag | u8 | the record type, from the tag table |
| a | u8 | the profile number, 1 to 5, on profile and slot records |
| b | u8 | the slot number, 1 to 8, on slot records |
| c | u8 | `0x08` on the slot kind record of a used slot; 0 on every other record |
| len | u16 | the length of the data, in bytes |
| data | len bytes | the value |

A string is cp1252 text that ends in one NUL, and its `len` counts the NUL. Macro source is a string, and keeps its own line endings, CRLF or LF. Other data has no NUL.

Where the tag table marks a field "—", the vendor app leaves it uninitialised, so its value changes from one save to the next. The CLI ignores the field when it reads, and writes 0 there.

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
| `0x11` | name of the vendor app's file of key aliases | highest profile number | — | string |
| `0x12` | name of the vendor app's file of macro names | highest profile number | — | string |
| `0x13` | unknown | highest profile number | — | 1 byte, seen as 0 |

Tags `0x08` to `0x0a`, `0x0d` to `0x0f`, and any tag above `0x13`, are unused.

`pedals.toml` keeps each record:

- tags `0x01`, `0x03`, `0x04` and `0x10`, and the slot records, in its own keys;
- tags `0x11` and `0x12` in the `[files]` table;
- tag `0x13`, and any unused tag, as `[[record]]` entries.

The serial number, tag `0x02`, stays on the pedals: `apply` copies it from the pedals' current image.

### Record order

The vendor app writes the records in this order, and so does the CLI. The CLI reads them in any order.

1. The owner name, then the serial number.
2. For each profile, from profile 1:
   1. its settings, name and background picture;
   2. for each slot from 1 to 8: the slot kind and the macro file name, then, in a used slot only, the label, the description and the macro source.
3. Tags `0x11`, `0x12` and `0x13`, then each `[[record]]` entry.

## The runtime image (space 3)

[pedals/compiler.py](../pedals/compiler.py) builds the runtime image, and [language.md](./language.md) gives its bytecode.

### Runtime image header

The header is 18 u32 fields, `0x48` bytes. Each table offset counts in bytes from the image start.

| Offset | Field |
| --- | --- |
| `0x00` | magic, `0xDEAD0BF0` |
| `0x04` | image length, in bytes |
| `0x08` | 0 |
| `0x0C` | 0 |
| `0x10` | thread table offset |
| `0x14` | thread table length: 12 bytes per thread |
| `0x18` | procedure table offset |
| `0x1C` | procedure table length: 4 bytes per procedure |
| `0x20` | string table offset |
| `0x24` | string table length |
| `0x28` | number of strings |
| `0x2C` | variable inits offset |
| `0x30` | variable inits length; the CLI writes none, so 0 |
| `0x34` | code offset |
| `0x38` | code length |
| `0x3C` | number of variables; the CLI writes 0 |
| `0x40` | number of threads |
| `0x44` | number of procedures |

### Tables and code

After the header come the thread table, the procedure table, the string table, then the code. Each thread is one pedal's macro, in pedal order from profile 1. A pedal with no macro has no thread.

- A thread entry is three u32 values: 0, the bit of the thread's profile (`1 << (profile - 1)`), and the thread's start, counted from the start of the code.
- A procedure entry is one u32: the procedure's start, counted from the start of the code.
- The string table starts with 8 bytes for each string: a u16 length that counts the NUL, 2 more bytes, and a u32 offset counted from the start of the string table. The strings follow, each with one NUL.
- The code starts at the first multiple of 4 at or after the end of the string table. It holds each macro's procedures, then its thread.

### Bytes the vendor app leaves unset

The vendor app sets the image length at `0x04` to the string bytes, plus the code, plus 4 × (procedures + 3 × threads + 2 × (strings + 10)). That length is 8 bytes longer than the header, tables and code need, less the padding before the code, so the image ends with up to 8 spare bytes. The CLI writes the same length.

The vendor app never writes these bytes, so their values change from one save to the next:

- the spare bytes at the end;
- the padding before the code;
- the 2 bytes after each string length.

The CLI writes 0 there.
