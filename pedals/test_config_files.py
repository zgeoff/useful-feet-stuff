import pytest

from pedals import config_files
from pedals.config_files import ConfigError, PullRefused
from pedals.profile_image import Config, Pedal, Profile, Record


def test_it_loads_the_config_it_saved(tmp_path):
    config = Config(
        owner="Test Owner",
        serial="",
        files={"aliases": "Aliases.txt"},
        profiles=[
            Profile(
                name="Racing Sim",
                settings=bytes(range(29)),
                image="sky.png",
                pedals=[
                    Pedal(macro="Horn.idi", source=b"PROCEDURE Horn\r\nEND", label="Horn", description=None),
                    Pedal(),
                    Pedal(macro="Wipers.idi", source=b"PROCEDURE Wipe\nEND", label="Wipers", description="Front"),
                    Pedal(),
                ],
            )
        ],
        extra=[Record(tag=0x13, a=1, b=0, c=0, data=b"\x00")],
    )
    config_files.save(config, tmp_path)

    assert config_files.load(tmp_path) == config


def test_save_writes_each_macro_byte_for_byte(tmp_path):
    source = b"// horn\r\nPROCEDURE Horn\r\nEND\r\n"
    config = Config(
        owner="", serial="", files={},
        profiles=[Profile(name="Racing Sim", settings=bytes(29), image=None,
                          pedals=[Pedal(macro="Horn.idi", source=source, label="Horn"), Pedal(), Pedal(), Pedal()])],
    )

    config_files.save(config, tmp_path)

    assert (tmp_path / "macros" / "Horn.idi").read_bytes() == source


def test_save_refuses_two_pedals_that_name_one_file_with_different_source(tmp_path):
    config = Config(
        owner="", serial="", files={},
        profiles=[Profile(name="Racing Sim", settings=bytes(29), image=None, pedals=[
            Pedal(macro="Horn.idi", source=b"one", label="Horn"),
            Pedal(macro="Horn.idi", source=b"two", label="Horn"),
            Pedal(), Pedal(),
        ])],
    )

    with pytest.raises(PullRefused, match="profile 1 pedal 1 and profile 1 pedal 2"):
        config_files.save(config, tmp_path)


@pytest.mark.parametrize("name", ["../escape.idi", "sub/dir.idi", "C:evil.idi", "..\\up.idi"])
def test_save_refuses_a_macro_name_that_is_not_a_plain_file_name(tmp_path, name):
    config = Config(
        owner="", serial="", files={},
        profiles=[Profile(name="Office", settings=bytes(29), image=None,
                          pedals=[Pedal(macro=name, source=b"x", label="x"), Pedal(), Pedal(), Pedal()])],
    )

    with pytest.raises(PullRefused, match="not a plain file name"):
        config_files.save(config, tmp_path)


def test_load_rejects_a_pedal_whose_macro_file_is_missing(tmp_path):
    (tmp_path / "pedals.toml").write_text(
        '[[profile]]\nname = "Office"\nsettings = "' + "00" * 29 + '"\n\n  [[profile.pedal]]\n  macro = "Gone.idi"\n'
    )

    with pytest.raises(ConfigError, match="macros/Gone.idi does not exist"):
        config_files.load(tmp_path)


def test_load_rejects_six_profiles(tmp_path):
    (tmp_path / "pedals.toml").write_text(
        "".join(f'[[profile]]\nname = "P{n}"\nsettings = "' + "00" * 29 + '"\n' for n in range(6))
    )

    with pytest.raises(ConfigError, match="6 profiles"):
        config_files.load(tmp_path)


def test_load_rejects_settings_that_are_not_29_bytes(tmp_path):
    (tmp_path / "pedals.toml").write_text('[[profile]]\nname = "Office"\nsettings = "0000"\n')

    with pytest.raises(ConfigError, match="2 bytes; must be 29"):
        config_files.load(tmp_path)


def test_load_reports_a_missing_pedals_toml(tmp_path):
    with pytest.raises(ConfigError, match="run `pedals pull` first"):
        config_files.load(tmp_path)
