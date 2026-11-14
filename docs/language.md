# Macro language

Each pedal runs a macro: a `.idi` text file in `macros/`, written in IDI, the macro language of the pedals' vendor app, `IDIConfig.exe`. `pedals.toml` names the macro each pedal runs. `pedals apply` compiles every macro into one runtime image for the pedals, with the same bytes the vendor app's compiler writes. When a macro uses anything outside the subset below, `pedals apply` stops with a compile error, and prints the macro file and the line.

## The subset

```text
PROCEDURE <name> … RETURN END      a procedure; it ends with RETURN, then END
THREAD <name> … END                the macro's thread; it runs while the macro's profile is active
<label>:          GOTO <label>     a label and a jump to it, inside one THREAD or PROCEDURE
DO … WHILE (<expression>)          a loop that runs again while the expression is true
<procedure>()                      a call to a procedure in the same macro file
// …                               a comment to the end of the line
```

A macro file holds its procedures and one thread. A profile is one set of 4 pedal macros, and the pedals run one profile at a time.

An expression holds decimal and `0x` hex literals, a string in double quotes, `Button`, `ButtonMask`, `GetButtonState`, parentheses, `&` and `==`. `==` binds tighter than `&`, as in C and in the vendor app's operator table, so put parentheses around a `&` you compare. An expression goes in a `WHILE` or in a builtin's arguments.

| Builtin | Arguments | Does |
| --- | --- | --- |
| `WaitForButton(button, mask)` | 2 | waits for the pedal press that `button` and `mask` select; the macros pass `Button, ButtonMask` |
| `DelayForMs(ms)` | 1 | waits `ms` milliseconds |
| `KeyActionHid(modifier, key, action)` | 3 | presses (`action` 1) or releases (`action` 0) a USB HID key |
| `MButton(a, b, c, d)` | 4 | sends a mouse button action; the vendor app defines the 4 values, so copy a call from a macro that works, such as `MButton(1,0,90,0)` |
| `TypeText("text", ms)` | 2 | types the text, with `ms` milliseconds between keys |
| `GetButtonState` | 0 | the current bit of each pedal that is down; write it with no parentheses |

`Button` and `ButtonMask` both hold the bit of the pedal that runs the macro: 1 for pedal 1, 2 for pedal 2, 4 for pedal 3 and 8 for pedal 4. The compiler writes the bit in as a constant, so one macro file works on any pedal. Take key codes and modifier bits from [reference/usb_hid_keys.h](../reference/usb_hid_keys.h). For two modifiers, add their bits.

## Bytecode

The opcodes below come from the vendor app's keyword table and its own disassembler. `pedals apply` writes the same bytes. Every byte value is hex, and every operand is little-endian.

| Bytes | Instruction |
| --- | --- |
| `00` | END |
| `01` | RETURN |
| `0b` | `==` on the top two values of the stack |
| `12` | `&` on the top two values of the stack |
| `80` + n | push n, for n from 0 to 127 |
| `44` + operand | push any other value |
| `42` + id | call the builtin with that id |
| `43` + n | call procedure n − 1, numbered from 0 across all macros on the pedals |
| `46` + offset | branch back to the `DO` when the top of the stack is true |
| `65` + 2-byte offset | `GOTO`; the vendor app always writes it as `45` in its 2-byte form |

Each opcode from `40` to `4f` takes a signed operand in the narrowest width that holds it, and the opcode carries the width:

| Opcode | Operand |
| --- | --- |
| op | 1 byte |
| op + `20` | 2 bytes |
| op + `10` | 3 bytes |
| op + `30` | 4 bytes |

A branch offset counts from the byte after the instruction.

A string is pushed as `80000000` plus the string's number, counted from 1 across all macros. The compiler stores the text of each `TypeText` call as a string of its own, even when two calls share the text.

| Builtin | Id |
| --- | --- |
| `GetButtonState` | `01` |
| `WaitForButton` | `0e` |
| `DelayForMs` | `0f` |
| `MButton` | `18` |
| `TypeText` | `1a` |
| `KeyActionHid` | `33` |
