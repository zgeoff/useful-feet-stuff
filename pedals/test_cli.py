import io
from pathlib import Path

import pytest
from datetime import datetime

from pedals import profile_image
from pedals.cli import Env, main
from pedals.profile_image import Record
from pedals.test_utils.fake_device import FakeDevice
from pedals.test_utils.images import build_image, profile_records, text

READ_SIDE_COMMANDS = {0x01, 0x0B, 0x0D, 0x02, 0x04}


def setup_test(tmp_path, fake: FakeDevice, vendor_app_running: bool = False, answer: bool = False):
    out = io.StringIO()
    asked: list[str] = []
    env = Env(
        open_hid=lambda: fake,
        vendor_app_running=lambda: vendor_app_running,
        repo_root=tmp_path / "repo",
        out=out,
        backup_root=tmp_path / "backups",
        ask=lambda question: asked.append(question) or answer,
        now=lambda: datetime(2026, 3, 1, 9, 30, 0),
    )
    (tmp_path / "repo").mkdir()
    return {
        "fake": fake,
        "root": tmp_path / "repo",
        "backups": tmp_path / "backups",
        "asked": asked,
        "out": out,
        "run": lambda *argv: (main(list(argv), env), out.getvalue()),
    }


def two_profile_image() -> bytes:
    return build_image(
        [
            Record(tag=0x01, a=0, b=0, c=0, data=text("Test Owner")),
            *profile_records(1, "Racing Sim", [("Horn.idi", b"PROCEDURE Horn\r\nEND", "Horn", None)]),
            *profile_records(2, "Office", [("Mute.idi", b"PROCEDURE Mute\nEND", "Mute", "Toggle mute"),
                                           ("Horn.idi", b"PROCEDURE Horn\r\nEND", "Horn", None)]),
        ]
    )


def test_status_prints_the_firmware_channel_and_active_profile(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}, active=2))

    assert ctx["run"]("status") == (
        0,
        'firmware   Sep 26 2020 14:06:10 Ver 1.0.8\nchannel    ok\nprofile    2 "Office"\n',
    )


def test_status_tells_the_owner_to_replug_a_silent_device(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(silent=True))

    code, out = ctx["run"]("status")

    assert (code, "replug the pedals' USB cable" in out) == (3, True)


def test_every_command_refuses_and_sends_nothing_while_the_vendor_app_runs(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}), vendor_app_running=True)

    code, out = ctx["run"]("status")

    assert (code, out, ctx["fake"].sent) == (
        6,
        "refused    IDIConfig.exe is running; close it first, since both read the same reports\n",
        [],
    )


def test_status_prints_the_version_then_refuses_old_style_firmware(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(new_style=False))

    assert ctx["run"]("status") == (
        6,
        "firmware   Sep 26 2020 14:06:10 Ver 1.0.8\n"
        "refused    old-style firmware; this tool supports only new-style firmware\n",
    )


def test_show_prints_one_profile_by_name(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))

    assert ctx["run"]("show", "Office") == (
        0,
        'profile 2 "Office"\n'
        "  pedal 1  Mute                Mute.idi\n"
        "  pedal 2  Horn                Horn.idi\n"
        "  pedal 3  (empty)\n"
        "  pedal 4  (empty)\n",
    )


def test_show_rejects_a_profile_number_the_device_lacks(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))

    assert ctx["run"]("show", "3") == (2, "profile    3 does not exist; the device has profiles 1 to 2\n")


def test_pull_writes_pedals_toml_and_each_named_macro(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))

    code, out = ctx["run"]("pull")

    assert (code, out, sorted(p.name for p in (ctx["root"] / "macros").iterdir())) == (
        0,
        "wrote      pedals.toml and 2 macros: Horn.idi, Mute.idi\n",
        ["Horn.idi", "Mute.idi"],
    )


def test_diff_reports_no_difference_right_after_a_pull(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))
    ctx["run"]("pull")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    assert ctx["run"]("diff") == (0, "same       the repo matches the device\n")


def test_diff_reports_a_changed_label_and_a_changed_source(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))
    ctx["run"]("pull")
    toml = ctx["root"] / "pedals.toml"
    toml.write_text(toml.read_text().replace('label = "Mute"', 'label = "Silence"'))
    (ctx["root"] / "macros" / "Horn.idi").write_bytes(b"PROCEDURE Honk\r\nEND")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    assert ctx["run"]("diff") == (
        1,
        "profile 1 pedal 1  source of Horn.idi differs\n"
        "profile 2 pedal 1  label: repo 'Silence', device 'Mute'\n"
        "profile 2 pedal 2  source of Horn.idi differs\n",
    )


def test_diff_notes_a_macro_file_no_pedal_names_without_failing(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))
    ctx["run"]("pull")
    (ctx["root"] / "macros" / "Spare.idi").write_bytes(b"x")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    assert ctx["run"]("diff") == (
        0,
        "same       the repo matches the device\nunused     macros/Spare.idi: no pedal names it\n",
    )


def test_diff_without_pedals_toml_fails_as_bad_input(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))

    assert ctx["run"]("diff") == (4, "config     pedals.toml: -: file not found; run `pedals pull` first\n")


def test_switch_by_name_sends_the_switch_command(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))

    code, out = ctx["run"]("switch", "Office")

    assert (code, out, ctx["fake"].sent[-1]) == (0, 'profile    2 "Office"\n', bytes([0x04, 0x01, 0x02]))


def test_switch_rejects_a_name_two_profiles_share(tmp_path):
    image = build_image([*profile_records(1, "Office", []), *profile_records(2, "Office", [])])
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: image}))

    assert ctx["run"]("switch", "Office") == (2, 'profile    "Office" matches profiles [1, 2]\n')


def test_the_read_side_commands_send_only_read_and_switch_commands(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))
    for argv in (["status"], ["show"], ["pull"], ["diff"], ["switch", "1"]):
        ctx["run"](*argv)

    assert {payload[0] for payload in ctx["fake"].sent} == READ_SIDE_COMMANDS


def test_a_bad_device_image_fails_as_bad_device_data(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: build_image([], magic=0x1)}))

    code, out = ctx["run"]("show")

    assert (code, out) == (7, "device     space 2 magic is 0x00000001, not 0x86754232\n")


GOLDEN = Path(__file__).parent / "test_fixtures" / "golden"


def golden_device(**kwargs) -> FakeDevice:
    return FakeDevice(spaces={2: (GOLDEN / "space2.bin").read_bytes(), 3: (GOLDEN / "space3.bin").read_bytes()},
                      **kwargs)


def relabel_pedal_1(ctx, label: str) -> None:
    toml = ctx["root"] / "pedals.toml"
    toml.write_text(toml.read_text().replace('label = "PushToTalk"', f'label = "{label}"', 1))


def test_apply_writes_the_repo_to_the_pedals_after_a_backup(tmp_path):
    ctx = setup_test(tmp_path, golden_device(active=1))
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    code, out = ctx["run"]("apply", "--yes")

    backup = ctx["backups"] / "20260301-093000"
    assert (code, out.splitlines()[-2:], ctx["run"]("diff")[0], ctx["fake"].running) == (
        0,
        [f"backup     {backup}", "wrote      1 profiles; the device matches the repo"],
        0,
        True,
    )
    assert ((backup / "space2.bin").read_bytes(), (backup / "space3.bin").read_bytes()) == (
        (GOLDEN / "space2.bin").read_bytes(),
        (GOLDEN / "space3.bin").read_bytes(),
    )


def test_apply_keeps_the_device_serial(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    ctx["run"]("apply", "--yes")

    assert profile_image.decode(ctx["fake"].stored(2, 0x2000)).serial == "F00000000"


def test_apply_sends_the_vendor_write_sequence(tmp_path):
    ctx = setup_test(tmp_path, golden_device(active=1))
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")
    ctx["fake"].sent.clear()

    ctx["run"]("apply", "--yes")

    flash_commands = [p[:3].hex() for p in ctx["fake"].sent if p[0] in (0x08, 0x05, 0x09, 0x04) or p[:2] == b"\x0d\x01"]
    start = flash_commands.index("08")
    control = [c for c in flash_commands if not c.startswith("0d")]
    assert (flash_commands[start : start + 4], control[control.index("08") :]) == (
        ["08", "0d0102", "050100", "050101"],
        ["08", "050100", "050101", "09", "040101"],
    )


def test_apply_writes_nothing_until_the_owner_says_yes(tmp_path):
    ctx = setup_test(tmp_path, golden_device(), answer=False)
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    code, out = ctx["run"]("apply")

    assert (code, out.splitlines()[-1], ctx["asked"], [p for p in ctx["fake"].sent if p[0] in (0x08, 0x03, 0x05)]) == (
        0,
        "stopped    nothing written",
        ["write this config to the pedals? [y/N] "],
        [],
    )


def test_apply_writes_nothing_when_the_repo_matches_the_device(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    ctx["run"]("pull")

    code, out = ctx["run"]("apply", "--yes")

    assert (code, out.splitlines()[-1], [p for p in ctx["fake"].sent if p[0] == 0x08]) == (
        0,
        "same       the repo matches the device; nothing to write",
        [],
    )


def test_apply_fails_as_bad_input_on_a_compile_error_before_any_write(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    ctx["run"]("pull")
    macro = ctx["root"] / "macros" / "PushToTalk.idi"
    macro.write_bytes(macro.read_bytes().replace(b"DelayForMs(16)", b"Beep(16)"))

    code, out = ctx["run"]("apply", "--yes")

    assert (code, "unknown procedure or builtin 'Beep'" in out, [p for p in ctx["fake"].sent if p[0] == 0x08]) == (
        4,
        True,
        [],
    )


def test_apply_retries_a_write_the_device_lost(tmp_path):
    ctx = setup_test(tmp_path, golden_device(lost_writes=2))
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    code, _ = ctx["run"]("apply", "--yes")

    assert (code, ctx["run"]("diff")[0]) == (0, 0)


def test_apply_stops_with_the_restore_command_after_3_failed_writes(tmp_path):
    ctx = setup_test(tmp_path, golden_device(lost_writes=3))
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    code, out = ctx["run"]("apply", "--yes")

    backup = ctx["backups"] / "20260301-093000"
    assert (code, out.splitlines()[-3:], ctx["fake"].running) == (
        5,
        [
            "flash      space 2 at 0x0 reads back wrong after 3 writes",
            "flash      the pedals' macros are stopped until a write succeeds",
            f'flash      to put the old config back, run: bin/pedals restore "{backup}"',
        ],
        False,
    )


def test_apply_puts_the_old_config_back_when_the_erase_misses_space_3(tmp_path):
    ctx = setup_test(tmp_path, golden_device(erase_clears_space3=False))
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    code, out = ctx["run"]("apply", "--yes")

    assert (code, out.splitlines()[-2], ctx["fake"].running, ctx["fake"].stored(2, 3488), ctx["fake"].stored(3, 332)) == (
        5,
        "flash      space 3 is not blank after the erase; the old config is back",
        True,
        (GOLDEN / "space2.bin").read_bytes(),
        (GOLDEN / "space3.bin").read_bytes(),
    )


def test_restore_writes_a_saved_pair_to_the_pedals(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")
    ctx["run"]("apply", "--yes")
    backup = ctx["backups"] / "20260301-093000"
    (ctx["backups"] / "kept").mkdir()
    for name in ("space2.bin", "space3.bin"):
        (ctx["backups"] / "kept" / name).write_bytes((backup / name).read_bytes())

    code, _ = ctx["run"]("restore", str(ctx["backups"] / "kept"), "--yes")

    assert (code, ctx["fake"].stored(2, 3488), ctx["fake"].stored(3, 332), ctx["fake"].running) == (
        0,
        (GOLDEN / "space2.bin").read_bytes(),
        (GOLDEN / "space3.bin").read_bytes(),
        True,
    )


def test_restore_fails_as_bad_argument_on_a_folder_without_a_pair(tmp_path):
    ctx = setup_test(tmp_path, golden_device())

    code, out = ctx["run"]("restore", str(tmp_path / "nothing"), "--yes")

    assert (code, out) == (2, f"restore    {tmp_path / 'nothing'} holds no space2.bin and space3.bin\n")


def test_apply_writes_in_the_vendor_chunks_of_56_bytes_inside_each_page(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")
    ctx["fake"].sent.clear()

    ctx["run"]("apply", "--yes")

    writes = [(int.from_bytes(p[4:8], "little"), int.from_bytes(p[2:4], "little")) for p in ctx["fake"].sent if p[0] == 0x03]
    assert writes[:6] == [(0x00, 56), (0x38, 56), (0x70, 56), (0xA8, 56), (0xE0, 32), (0x100, 56)]


def test_restore_refuses_a_backup_shorter_than_its_header_says(tmp_path):
    ctx = setup_test(tmp_path, golden_device())
    (ctx["backups"] / "cut").mkdir(parents=True)
    (ctx["backups"] / "cut" / "space2.bin").write_bytes((GOLDEN / "space2.bin").read_bytes())
    (ctx["backups"] / "cut" / "space3.bin").write_bytes((GOLDEN / "space3.bin").read_bytes()[:72])

    code, out = ctx["run"]("restore", str(ctx["backups"] / "cut"), "--yes")

    assert (code, "space 3 image claims 332 bytes; the file holds 72" in out, [p for p in ctx["fake"].sent if p[0] == 0x08]) == (
        7,
        True,
        [],
    )


class FailingWrites(FakeDevice):
    def __init__(self, failure: str, **kwargs):
        super().__init__(**kwargs)
        self.failure = failure

    def _answer(self, payload):
        if payload[0] == 0x03 and self.failure == "timeout":
            return None
        if payload[0] == 0x03 and self.failure == "status":
            return bytes([0x83, 0x01, 0x01])
        return super()._answer(payload)


@pytest.mark.parametrize("failure", ["timeout", "status"])
def test_apply_prints_the_restore_command_when_a_write_gets_no_good_answer(tmp_path, failure):
    fake = FailingWrites(failure, spaces={2: (GOLDEN / "space2.bin").read_bytes(), 3: (GOLDEN / "space3.bin").read_bytes()})
    ctx = setup_test(tmp_path, fake)
    ctx["run"]("pull")
    relabel_pedal_1(ctx, "Talk")

    code, out = ctx["run"]("apply", "--yes")

    backup = ctx["backups"] / "20260301-093000"
    assert (code, out.splitlines()[-1]) == (5, f'flash      to put the old config back, run: bin/pedals restore "{backup}"')


def test_compiler_binds_equality_tighter_than_and_as_the_vendor_table_does():
    from pedals import compiler
    from pedals.test_compiler import code_of, config_of

    code = code_of(compiler.compile(config_of([b"THREAD Check\nDelayForMs(1 & 2 == 0)\nEND\n"])))

    assert code.hex() == "8182800b12420f00"
