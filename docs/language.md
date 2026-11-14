# Macro language

The pedals hold up to 5 profiles and run one at a time. A profile gives each of the 4 pedals a macro: a `.idi` text file in `macros/`, written in IDI, the macro language of the vendor app, `IDIConfig.exe`. [cli.md](cli.md#pedalstoml) shows how `pedals.toml` lists the profiles and the macro each pedal runs. `pedals switch` changes the active profile.

`pedals apply` compiles every macro into one runtime image, with the same bytes as the vendor app's compiler. When a macro uses anything outside the subset below, `pedals apply` stops with a compile error, and prints the macro file and the line.

## The subset

```text
PROCEDURE <name> … RETURN END      a procedure; it ends with RETURN, then END
THREAD <name> … END                the macro's thread; it runs while the macro's profile is active
<label>:          GOTO <label>     a label and a jump to it, inside one THREAD or PROCEDURE
DO … WHILE (<expression>)          a loop that runs again while the expression is true
<procedure>()                      a call to a procedure in the same macro file
// …                               a comment to the end of the line
```

A macro file holds its procedures and one thread.

An expression holds decimal and `0x` hex literals, a string in double quotes, `Button`, `ButtonMask`, `GetButtonState`, parentheses, `&` and `==`. `==` binds tighter than `&`, as in C and in the vendor app's operator table. Put parentheses around a `&` you compare. An expression goes in a `WHILE` or in a builtin's arguments.

| Builtin | Arguments | Does |
| --- | --- | --- |
| `WaitForButton(button, mask)` | 2 | waits for a pedal press; pass `Button, ButtonMask` to wait for this macro's pedal |
| `DelayForMs(ms)` | 1 | waits `ms` milliseconds |
| `KeyActionHid(modifier, key, action)` | 3 | presses (`action` 1) or releases (`action` 0) a USB HID key |
| `MButton(a, b, c, d)` | 4 | sends a mouse action |
| `TypeText("text", ms)` | 2 | types the text, with `ms` milliseconds between keys |
| `GetButtonState` | 0 | a bit mask of the pedals that are down |

Write `GetButtonState` with no parentheses. `macros/RepeatLeftClick.idi` and `macros/SpamClick.idi` call `MButton(1,0,90,0)` to send a left click. The vendor app defines the meaning of each value, and this repo records no other call.

`Button` and `ButtonMask` both hold the bit of the pedal that runs the macro: 1 for pedal 1, 2 for pedal 2, 4 for pedal 3 and 8 for pedal 4. `pedals apply` writes the bit in as a constant, so one macro file works on any pedal. Take key codes and modifier bits from [reference/usb_hid_keys.h](../reference/usb_hid_keys.h). For two modifiers, add their bits.

## Bytecode

The opcodes come from the vendor app's keyword table and its own disassembler. Every byte value below is hex, and every operand is little-endian.

| Bytes | Instruction |
| --- | --- |
| `00` | END |
| `01` | RETURN |
| `0b` | `==` on the top two values of the stack |
| `12` | `&` on the top two values of the stack |
| one byte, `80` to `ff` | push the byte minus `80`: 0 to 127 |
| `44`, then an operand | push any other value |
| `42`, then an id | call the builtin with that id |
| `43`, then the procedure's number plus 1 | call a procedure |
| `46`, then an offset | branch back to the `DO` when the top of the stack is true |
| `45`, then an offset | `GOTO` |

### Operand widths

Each opcode from `40` to `4f` takes a signed operand. The compiler picks the narrowest width that holds the value, and adds a width flag to the opcode:

| Opcode byte | Operand |
| --- | --- |
| the opcode | 1 byte |
| the opcode plus `20` | 2 bytes |
| the opcode plus `10` | 3 bytes |
| the opcode plus `30` | 4 bytes |

`GOTO` breaks that rule. The vendor app always writes it with a 2-byte offset, as `65`. A `GOTO` or `46` offset counts from the byte after the instruction.

### Numbering

The compiler takes the macros in pedal order, from pedal 1 of profile 1 to pedal 4 of the last profile. Procedures are numbered from 0 in that order. Strings are numbered from 1 in the same order, and the compiler gives each `TypeText` call a string of its own, even when two calls share the text. A string is pushed as `44` with a 4-byte operand, `80000000` plus the string's number. [image-format.md](image-format.md#the-runtime-image-space-3) gives where the strings and procedures sit in the runtime image.

| Builtin | Id |
| --- | --- |
| `GetButtonState` | `01` |
| `WaitForButton` | `0e` |
| `DelayForMs` | `0f` |
| `MButton` | `18` |
| `TypeText` | `1a` |
| `KeyActionHid` | `33` |
