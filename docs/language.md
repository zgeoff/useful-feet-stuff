# Macro language

The pedals run macros written in IDI, the vendor app's macro language. `pedals apply` compiles each macro to the same bytecode the vendor app's compiler writes. It accepts the subset of IDI below and rejects anything else with a compile error that names the macro file and the line.

## The subset

```text
PROCEDURE <name> … RETURN END      a procedure; it ends with RETURN, then END
THREAD <name> … END                the pedal's thread; it starts when the profile does
<label>:          GOTO <label>     a label and a jump to it, inside one THREAD or PROCEDURE
DO … WHILE (<expression>)          a loop that runs while the expression is true
<procedure>()                      a call to a procedure in the same macro file
// …                               a comment to the end of the line
```

An expression holds decimal and `0x` hex literals, `Button`, `ButtonMask`, `GetButtonState`, parentheses, `&` and `==`. `&` binds tighter than `==`.

| Builtin | Arguments | Does |
| --- | --- | --- |
| `WaitForButton(button, mask)` | 2 | waits until the pedals match the button bits under the mask |
| `DelayForMs(ms)` | 1 | waits `ms` milliseconds |
| `KeyActionHid(modifier, key, action)` | 3 | presses (`action` 1) or releases (`action` 0) a USB HID key |
| `MButton(a, b, c, d)` | 4 | sends a mouse button action |
| `TypeText("text", ms)` | 2 | types the text, with `ms` milliseconds between keys |
| `GetButtonState` | 0 | the pedals' current button bits, in an expression |

`Button` and `ButtonMask` are the bit of the pedal that runs the macro: 1 for pedal 1, 2 for pedal 2, 4 for pedal 3 and 8 for pedal 4. Take key codes and modifier bits from [reference/usb_hid_keys.h](../reference/usb_hid_keys.h). For two modifiers, add their bits.

## Bytecode

The vendor app's keyword table and its own disassembler give these opcodes. The compiler writes the same bytes.

| Bytes | Instruction |
| --- | --- |
| `00` | END |
| `01` | RETURN |
| `0b`, `12` | `==`, `&`, applied to the top two values on the stack |
| `80 + n` | push `n`, for `n` from 0 to 127 |
| `44 <operand>` | push any other value |
| `42 <id>` | call the builtin with that id |
| `43 <n>` | call procedure `n - 1`, counted over the whole image |
| `46 <offset>` | branch back to the `DO` when the value on the stack is true |
| `65 <offset:i16>` | `GOTO`, always with a 16-bit offset |

Each opcode from `0x40` to `0x4f` takes a signed operand in the narrowest width that holds it. The opcode itself carries the width: no flag for 1 byte, `+0x20` for 2 bytes, `+0x10` for 3 bytes, and `+0x30` for 4 bytes. A branch offset counts from the byte after the instruction.

A string literal is pushed as `0x80000000` plus the string's number in the image, counted from 1. Each `TypeText` call adds its own string, even when the text repeats.

The builtin ids are `0x01` `GetButtonState`, `0x0e` `WaitForButton`, `0x0f` `DelayForMs`, `0x18` `MButton`, `0x1a` `TypeText` and `0x33` `KeyActionHid`.
