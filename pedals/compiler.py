"""Config → the space 3 runtime image, matching the vendor app's compiler.

The language subset lives in docs/language.md, and the image layout in docs/image-format.md.
Opcodes, builtin ids and widths come from the vendor app's own keyword table and disassembler.
"""

import re
import struct
from dataclasses import dataclass, field

from pedals.profile_image import Config, TooLarge

MAGIC = 0xDEAD0BF0
MAX_IMAGE_LEN = 0xC000
HEADER_LEN = 0x48

OP_END = 0x00
OP_RETURN = 0x01
OP_PUSH_SHORT = 0x80  # | n, for 0 <= n < 0x80
OP_CALL_BUILTIN = 0x42
OP_CALL_PROC = 0x43
OP_PUSH = 0x44
OP_BRANCH_TRUE = 0x46
OP_GOTO16 = 0x65  # the vendor app always writes GOTO with a 16-bit offset
STRING_FLAG = 0x80000000

OPERATORS = {"&": (0x12, 5), "==": (0x0B, 6)}  # opcode, precedence

# name → (id, argument count); from the vendor app's keyword table
BUILTINS = {
    "GetButtonState": (0x01, 0),
    "WaitForButton": (0x0E, 2),
    "DelayForMs": (0x0F, 1),
    "MButton": (0x18, 4),
    "TypeText": (0x1A, 2),
    "KeyActionHid": (0x33, 3),
}
PEDAL_CONSTANTS = ("Button", "ButtonMask")


class CompileError(Exception):
    def __init__(self, macro: str, line: int, message: str):
        super().__init__(f"{macro}:{line}: {message}")
        self.macro, self.line, self.message = macro, line, message


@dataclass
class _Image:
    code: bytearray = field(default_factory=bytearray)
    procs: list[int] = field(default_factory=list)
    threads: list[tuple[int, int]] = field(default_factory=list)  # (profile mask, code offset)
    strings: list[bytes] = field(default_factory=list)


def compile(config: Config) -> bytes:  # noqa: A001 - the design names it compiler.compile
    image = _Image()
    for p, profile in enumerate(config.profiles, 1):
        for k, pedal in enumerate(profile.pedals, 1):
            if pedal.macro is None:
                continue
            source = (pedal.source or b"").decode("cp1252")
            _Macro(image, pedal.macro, source, profile_mask=1 << (p - 1), button=1 << (k - 1)).compile()
    return _layout(image)


def _layout(image: _Image) -> bytes:
    nthr, nproc, nstr = len(image.threads), len(image.procs), len(image.strings)
    str_bytes = sum(len(s) + 1 for s in image.strings)
    size = str_bytes + len(image.code) + (nproc + nthr * 3 + (nstr + 10) * 2) * 4
    if size > MAX_IMAGE_LEN:
        raise TooLarge(f"space 3 image is {size} bytes; the limit is {MAX_IMAGE_LEN}")
    thr_off = HEADER_LEN
    proc_off = thr_off + nthr * 12
    str_off = proc_off + nproc * 4
    str_len = str_bytes + nstr * 8
    code_off = str_off + ((str_len + 3) & ~3)

    table, data = bytearray(), bytearray()
    for s in image.strings:
        table += struct.pack("<HHI", len(s) + 1, 0, nstr * 8 + len(data))  # the vendor app leaves the second u16 uninitialised
        data += s + b"\0"
    words = [MAGIC, size, 0, 0, thr_off, nthr * 12, proc_off, nproc * 4, str_off, str_len, nstr,
             code_off, 0, code_off, len(image.code), 0, nthr, nproc]
    out = bytearray(struct.pack("<18I", *words))
    for mask, offset in image.threads:
        out += struct.pack("<III", 0, mask, offset)
    for offset in image.procs:
        out += struct.pack("<I", offset)
    out += table + data
    out += bytes(code_off - len(out))
    out += image.code
    out += bytes(size - len(out))  # slack the vendor app sizes in but never writes
    return bytes(out)


_TOKEN = re.compile(r'\s*(?:(0x[0-9a-fA-F]+|\d+)|("[^"]*")|([A-Za-z_]\w*)|(==|[&(),]))')


class _Macro:
    def __init__(self, image: _Image, name: str, source: str, profile_mask: int, button: int):
        self.img, self.name, self.source = image, name, source
        self.mask, self.button = profile_mask, button
        self.procs: dict[str, int] = {}
        self.line = 0

    def error(self, message: str) -> CompileError:
        return CompileError(self.name, self.line, message)

    def compile(self) -> None:
        lines = [(n, re.sub(r"//.*", "", text).strip()) for n, text in enumerate(self.source.splitlines(), 1)]
        lines = [(n, text) for n, text in lines if text]
        # procedures can be called before they are defined
        base = len(self.img.procs)
        for n, text in lines:
            m = re.fullmatch(r"PROCEDURE\s+(\w+)", text)
            if m:
                self.line = n
                if m[1] in self.procs:
                    raise self.error(f"procedure {m[1]} is defined twice")
                self.procs[m[1]] = base + len(self.procs)
        i = 0
        while i < len(lines):
            self.line, text = lines[i]
            if re.fullmatch(r"PROCEDURE\s+\w+", text):
                self.img.procs.append(len(self.img.code))
                i = self.body(lines, i + 1, is_proc=True)
            elif re.fullmatch(r"THREAD\s+\w+", text):
                self.img.threads.append((self.mask, len(self.img.code)))
                i = self.body(lines, i + 1, is_proc=False)
            else:
                raise self.error(f"expected PROCEDURE or THREAD, found {text!r}")

    def body(self, lines, i: int, is_proc: bool) -> int:
        code = self.img.code
        labels: dict[str, int] = {}
        gotos: list[tuple[int, str, int]] = []  # operand position, label, line
        loops: list[int] = []
        returned = False
        while i < len(lines):
            self.line, text = lines[i]
            i += 1
            if text == "END":
                if loops:
                    raise self.error("DO without WHILE")
                if is_proc and not returned:
                    raise self.error("a PROCEDURE ends with RETURN before END")
                code.append(OP_END)
                for pos, label, line in gotos:
                    if label not in labels:
                        self.line = line
                        raise self.error(f"GOTO {label}: no such label")
                    struct.pack_into("<h", code, pos, labels[label] - (pos + 2))
                return i
            returned = False
            if m := re.fullmatch(r"(\w+):", text):
                if m[1] in labels:
                    raise self.error(f"label {m[1]} is defined twice")
                labels[m[1]] = len(code)
            elif m := re.fullmatch(r"GOTO\s+(\w+)", text):
                code.append(OP_GOTO16)
                gotos.append((len(code), m[1], self.line))
                code += b"\0\0"
            elif text == "DO":
                loops.append(len(code))
            elif m := re.fullmatch(r"WHILE\s*(\(.*\))", text):
                if not loops:
                    raise self.error("WHILE without DO")
                self.expression(m[1])
                self.branch_back(OP_BRANCH_TRUE, loops.pop())
            elif text == "RETURN":
                if not is_proc:
                    raise self.error("RETURN outside a PROCEDURE")
                code.append(OP_RETURN)
                returned = True
            else:
                self.call_statement(text)
        raise self.error("missing END")

    def branch_back(self, op: int, target: int) -> None:
        here = len(self.img.code)
        short = target - (here + 2)
        if short >= -0x80:
            self.emit(op, short)
        else:
            self.emit(op, target - (here + 3))

    def call_statement(self, text: str) -> None:
        toks = self.tokens(text)
        pos = self.call(toks, 0, statement=True)
        if pos != len(toks):
            raise self.error(f"unexpected {toks[pos][1]!r}")

    # --- expressions -------------------------------------------------------------------------

    def tokens(self, text: str) -> list[tuple[str, str]]:
        out, pos = [], 0
        while pos < len(text):
            if text[pos:].strip() == "":
                break
            m = _TOKEN.match(text, pos)
            if not m:
                raise self.error(f"cannot read {text[pos:].strip()!r}")
            kind = ("num", "str", "name", "op")[m.lastindex - 1]
            out.append((kind, m[m.lastindex]))
            pos = m.end()
        return out

    def expression(self, text: str) -> None:
        toks = self.tokens(text)
        pos = self.binary(toks, 0, 0)
        if pos != len(toks):
            raise self.error(f"unexpected {toks[pos][1]!r}")

    def binary(self, toks, pos: int, min_prec: int) -> int:
        pos = self.operand(toks, pos)
        while pos < len(toks) and toks[pos][1] in OPERATORS:
            op, prec = OPERATORS[toks[pos][1]]
            if prec < min_prec:
                break
            pos = self.binary(toks, pos + 1, prec + 1)
            self.img.code.append(op)
        return pos

    def operand(self, toks, pos: int) -> int:
        if pos >= len(toks):
            raise self.error("expression ends early")
        kind, value = toks[pos]
        if value == "(":
            pos = self.binary(toks, pos + 1, 0)
            return self.expect(toks, pos, ")")
        if kind == "num":
            self.push(int(value, 0))
            return pos + 1
        if kind == "str":
            self.img.strings.append(value[1:-1].encode("cp1252"))
            self.push(STRING_FLAG | len(self.img.strings))
            return pos + 1
        if kind == "name" and value in PEDAL_CONSTANTS:
            self.push(self.button)
            return pos + 1
        if kind == "name" and value in BUILTINS:
            return self.call(toks, pos, statement=False)
        raise self.error(f"unknown name {value!r}")

    def call(self, toks, pos: int, statement: bool) -> int:
        kind, name = toks[pos]
        if kind != "name":
            raise self.error(f"expected a call, found {name!r}")
        has_parens = pos + 1 < len(toks) and toks[pos + 1][1] == "("
        args = 0
        pos += 1
        if has_parens:
            pos += 1
            if toks[pos:pos + 1] != [("op", ")")]:
                while True:
                    pos = self.binary(toks, pos, 0)
                    args += 1
                    if pos < len(toks) and toks[pos][1] == ",":
                        pos += 1
                        continue
                    break
            pos = self.expect(toks, pos, ")")
        if name in self.procs:
            if not statement or args:
                raise self.error(f"procedure {name} takes no arguments and returns nothing")
            self.emit(OP_CALL_PROC, self.procs[name] + 1)
            return pos
        if name not in BUILTINS:
            raise self.error(f"unknown procedure or builtin {name!r}")
        ident, argc = BUILTINS[name]
        if args != argc:
            raise self.error(f"{name} takes {argc} arguments, not {args}")
        if statement and argc == 0:
            raise self.error(f"{name} returns a value; use it in an expression")
        if statement and not has_parens:
            raise self.error(f"{name} needs ( )")
        self.emit(OP_CALL_BUILTIN, ident)
        return pos

    def expect(self, toks, pos: int, value: str) -> int:
        if pos >= len(toks) or toks[pos][1] != value:
            raise self.error(f"expected {value!r}")
        return pos + 1

    # --- encoding ----------------------------------------------------------------------------

    def push(self, value: int) -> None:
        if not -0x80000000 <= value <= 0xFFFFFFFF:
            raise self.error(f"literal {value} does not fit in 32 bits")
        if 0 <= value < 0x80:
            self.img.code.append(OP_PUSH_SHORT | value)
        else:
            self.emit(OP_PUSH, value)

    def emit(self, op: int, value: int) -> None:
        """An opcode and its operand in the narrowest signed width, as the vendor app writes it."""
        v = value & 0xFFFFFFFF
        if v & 0xFFFFFF80 in (0, 0xFFFFFF80):
            self.img.code += bytes([op]) + v.to_bytes(4, "little")[:1]
        elif v & 0xFFFF8000 in (0, 0xFFFF8000):
            self.img.code += bytes([op | 0x20]) + v.to_bytes(4, "little")[:2]
        elif v & 0xFF800000 in (0, 0xFF800000):
            self.img.code += bytes([op | 0x10]) + v.to_bytes(4, "little")[:3]
        else:
            self.img.code += bytes([op | 0x30]) + v.to_bytes(4, "little")
