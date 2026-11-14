import io

from pedals.cli import Env, main
from pedals.profile_image import Record
from pedals.test_utils.fake_device import FakeDevice
from pedals.test_utils.images import build_image, profile_records, text

READ_SIDE_COMMANDS = {0x01, 0x0B, 0x0D, 0x02, 0x04}


def setup_test(tmp_path, fake: FakeDevice, vendor_app_running: bool = False):
    out = io.StringIO()
    env = Env(open_hid=lambda: fake, vendor_app_running=lambda: vendor_app_running, repo_root=tmp_path, out=out)
    return {"fake": fake, "root": tmp_path, "out": out, "run": lambda *argv: (main(list(argv), env), out.getvalue())}


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

    assert (code, out, sorted(p.name for p in (tmp_path / "macros").iterdir())) == (
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
    toml = tmp_path / "pedals.toml"
    toml.write_text(toml.read_text().replace('label = "Mute"', 'label = "Silence"'))
    (tmp_path / "macros" / "Horn.idi").write_bytes(b"PROCEDURE Honk\r\nEND")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    assert ctx["run"]("diff") == (
        1,
        "profile 1 pedal 1  source of Horn.idi differs\n"
        "profile 2 pedal 1  label: repo 'Silence', device 'Mute'\n"
        "profile 2 pedal 2  source of Horn.idi differs\n",
    )


def test_diff_lists_a_macro_file_no_pedal_names(tmp_path):
    ctx = setup_test(tmp_path, FakeDevice(spaces={2: two_profile_image()}))
    ctx["run"]("pull")
    (tmp_path / "macros" / "Spare.idi").write_bytes(b"x")
    ctx["out"].truncate(0)
    ctx["out"].seek(0)

    assert ctx["run"]("diff") == (1, "unused     macros/Spare.idi: no pedal names it\n")


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
