import struct
from pathlib import Path

import pytest

from pedals import compiler, profile_image
from pedals.compiler import CompileError
from pedals.profile_image import Config, Pedal, Profile, TooLarge

GOLDEN = Path(__file__).parent / "test_fixtures" / "golden"
# A 5-profile vendor pair from the owner's pedals. It holds the real serial, so it stays out of the repo.
LOCAL_PAIR = Path("/mnt/c/Users/Public/Public Hardware/GWS/pedal-restore/20261114-111836")

THREAD = b"""THREAD Profile
Start:
\tWaitForButton(Button, ButtonMask)
\tButtonDown()
\tGOTO Start
END
"""


def config_of(*profiles: list[bytes | None]) -> Config:
    return Config(
        owner="Test Owner",
        serial="F00000000",
        files={},
        profiles=[
            Profile(
                name=f"Profile {n}",
                settings=bytes(29),
                image=None,
                pedals=[Pedal() if src is None else Pedal(macro=f"M{n}{k}.idi", source=src, label="x")
                        for k, src in enumerate(sources, 1)],
            )
            for n, sources in enumerate(profiles, 1)
        ],
    )


def code_of(runtime: bytes) -> bytes:
    offset, length = struct.unpack_from("<II", runtime, 0x34)
    return runtime[offset : offset + length]


def proc(body: str) -> bytes:
    return f"PROCEDURE ButtonDown\n{body}\nRETURN\nEND\n".encode() + THREAD


def test_it_compiles_the_golden_config_to_the_vendor_runtime_byte_for_byte():
    config = profile_image.decode((GOLDEN / "space2.bin").read_bytes())

    assert compiler.compile(config) == (GOLDEN / "space3.bin").read_bytes()


@pytest.mark.skipif(not LOCAL_PAIR.is_dir(), reason="the owner's 5-profile pair is only on their PC")
def test_it_compiles_the_5_profile_config_to_the_vendor_runtime_apart_from_unset_bytes():
    space2 = (LOCAL_PAIR / "space2.bin").read_bytes()
    vendor = (LOCAL_PAIR / "space3.bin").read_bytes()
    vendor = vendor[: struct.unpack_from("<I", vendor, 4)[0]]

    ours = compiler.compile(profile_image.decode(space2[: profile_image.image_length(space2)]))

    assert len(ours) == len(vendor)
    assert [i for i in range(len(ours)) if ours[i] != vendor[i] and i not in unset_bytes(vendor)] == []


def unset_bytes(runtime: bytes) -> set[int]:
    """Bytes the vendor app sizes in but never writes: string-length high halves, padding, tail."""
    size = struct.unpack_from("<I", runtime, 4)[0]
    str_off, str_len, count, _, _, code_off, code_len = struct.unpack_from("<7I", runtime, 0x20)
    unset = {str_off + 8 * i + j for i in range(count) for j in (2, 3)}
    unset |= set(range(str_off + str_len, code_off))
    return unset | set(range(code_off + code_len, size))


def test_it_gives_each_profile_its_thread_mask_and_each_pedal_its_button():
    config = config_of([None, proc("DelayForMs(1)")], [None, None, proc("DelayForMs(1)")])

    runtime = compiler.compile(config)

    threads = [struct.unpack_from("<III", runtime, 0x48 + 12 * i) for i in range(2)]
    code = code_of(runtime)
    assert ([t[:2] for t in threads], code[threads[0][2] : threads[0][2] + 2], code[threads[1][2] : threads[1][2] + 2]) == (
        [(0, 1), (0, 2)],
        bytes([0x82, 0x82]),
        bytes([0x84, 0x84]),
    )


@pytest.mark.parametrize(
    ("literal", "encoded"),
    [
        ("0x7f", "ff"),
        ("128", "648000"),
        ("0x1234", "643412"),
        ("0x123456", "54563412"),
        ("0x12345678", "7478563412"),
    ],
)
def test_it_pushes_literal_in_the_narrowest_width(literal, encoded):
    runtime = compiler.compile(config_of([proc(f"DelayForMs({literal})")]))

    assert code_of(runtime)[:-1].hex().startswith(encoded + "420f")


def test_it_numbers_strings_from_1_and_stores_each_one():
    runtime = compiler.compile(config_of([proc('TypeText("ab",5)'), proc('TypeText("ab",5)')]))

    str_off, str_len, count = struct.unpack_from("<3I", runtime, 0x20)
    code = code_of(runtime)
    assert (count, runtime[str_off : str_off + str_len], code[:5], code.count(bytes.fromhex("7402000080"))) == (
        2,
        struct.pack("<HHIHHI", 3, 0, 16, 3, 0, 19) + b"ab\0ab\0",
        bytes.fromhex("7401000080"),
        1,
    )


def test_it_branches_back_with_a_16_bit_offset_over_a_long_loop_body():
    body = "DO\n" + "DelayForMs(1)\n" * 50 + "WHILE ((GetButtonState & ButtonMask) == Button)"

    code = code_of(compiler.compile(config_of([proc(body)])))

    # DO starts at 0; the branch is the 3 bytes before RETURN, END
    branch = code[150 + 6 : 150 + 9]
    assert branch == bytes([0x66]) + struct.pack("<h", 0 - (150 + 6 + 3))


def test_it_leaves_an_empty_pedal_without_a_thread():
    runtime = compiler.compile(config_of([None, None, None, proc("DelayForMs(1)")]))

    assert struct.unpack_from("<2I", runtime, 0x40) == (1, 1)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (proc("Beep(1)"), "unknown procedure or builtin 'Beep'"),
        (proc("DelayForMs(1, 2)"), "DelayForMs takes 1 arguments, not 2"),
        (proc("IF (Button == 1)"), "unknown procedure or builtin 'IF'"),
        (b"PROCEDURE ButtonDown\nDelayForMs(1)\nEND\n" + THREAD, "a PROCEDURE ends with RETURN before END"),
        (b"PROCEDURE ButtonDown\nRETURN\nEND\nTHREAD Profile\nGOTO Nowhere\nEND\n", "GOTO Nowhere: no such label"),
        (b"PROCEDURE ButtonDown\nRETURN\n", "missing END"),
    ],
)
def test_it_rejects_source_outside_the_supported_language(source, message):
    with pytest.raises(CompileError, match=message):
        compiler.compile(config_of([source]))


def test_it_names_the_macro_and_line_of_a_compile_error():
    with pytest.raises(CompileError) as err:
        compiler.compile(config_of([proc("Beep(1)")]))

    assert (err.value.macro, err.value.line) == ("M11.idi", 2)


def test_it_rejects_a_runtime_over_the_space_3_limit():
    body = "DelayForMs(1)\n" * 17000

    with pytest.raises(TooLarge, match="space 3 image"):
        compiler.compile(config_of([proc(body)]))
