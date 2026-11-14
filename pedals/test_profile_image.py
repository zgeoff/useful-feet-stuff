import pytest

from pedals import profile_image
from pedals.profile_image import BadImage, Config, Pedal, Profile, Record
from pedals.test_utils.images import build_image, profile_records, text


def test_it_decodes_owner_files_profiles_and_pedals():
    image = build_image(
        [
            Record(tag=0x01, a=0, b=0, c=0, data=text("Test Owner")),
            Record(tag=0x02, a=0, b=0, c=0, data=text("F12345678")),
            *profile_records(1, "Racing Sim", [("Horn.idi", b"PROCEDURE Horn\r\nRETURN\r\nEND", "Horn", "Sound the horn")]),
            Record(tag=0x11, a=1, b=0, c=0, data=text("Aliases.txt")),
            Record(tag=0x12, a=1, b=0, c=0, data=text("Macros.txt")),
        ]
    )

    assert profile_image.decode(image) == Config(
        owner="Test Owner",
        serial="F12345678",
        files={"aliases": "Aliases.txt", "macros": "Macros.txt"},
        profiles=[
            Profile(
                name="Racing Sim",
                settings=bytes(29),
                image=None,
                pedals=[
                    Pedal(macro="Horn.idi", source=b"PROCEDURE Horn\r\nRETURN\r\nEND", label="Horn", description="Sound the horn"),
                    Pedal(),
                    Pedal(),
                    Pedal(),
                ],
            )
        ],
        extra=[],
    )


def test_it_decodes_a_pedal_without_a_description_record_as_none():
    image = build_image(profile_records(1, "Office", [("Mute.idi", b"x", "Mute", None)]))

    assert profile_image.decode(image).profiles[0].pedals[0].description is None


def test_it_decodes_the_profile_image_record():
    image = build_image(
        [*profile_records(1, "Office", []), Record(tag=0x10, a=1, b=0, c=0, data=text("sky.png"))]
    )

    assert profile_image.decode(image).profiles[0].image == "sky.png"


def test_it_keeps_records_of_unknown_tags_in_device_order():
    image = build_image(
        [
            *profile_records(1, "Office", []),
            Record(tag=0x13, a=1, b=0, c=0, data=b"\x00"),
            Record(tag=0x2A, a=0, b=7, c=9, data=b"\x01\x02"),
        ]
    )

    assert profile_image.decode(image).extra == [
        Record(tag=0x13, a=1, b=0, c=0, data=b"\x00"),
        Record(tag=0x2A, a=0, b=7, c=9, data=b"\x01\x02"),
    ]


def test_it_decodes_cp1252_text():
    image = build_image(profile_records(1, "Café", []))

    assert profile_image.decode(image).profiles[0].name == "Café"


def test_it_rejects_an_image_with_the_wrong_magic():
    image = build_image(profile_records(1, "Office", []), magic=0x12345678)

    with pytest.raises(BadImage, match="magic"):
        profile_image.decode(image)


def test_it_rejects_an_image_with_an_unknown_version():
    image = build_image(profile_records(1, "Office", []), version=2)

    with pytest.raises(BadImage, match="version"):
        profile_image.decode(image)


def test_image_length_rejects_a_header_that_claims_more_than_128_kib():
    header = build_image([])[:0x0C] + (128 * 1024).to_bytes(4, "little") + bytes(0x54 - 0x10)

    with pytest.raises(BadImage, match="limit"):
        profile_image.image_length(header)


def test_it_rejects_a_macro_in_slot_5():
    records = profile_records(1, "Office", [])
    records.append(Record(tag=0x06, a=1, b=5, c=0, data=text("Extra.idi")))

    with pytest.raises(BadImage, match="slot 5"):
        profile_image.decode(build_image(records))


def test_it_rejects_a_record_that_runs_past_the_image_end():
    image = build_image(profile_records(1, "Office", []))
    cut = image[:-1]
    cut = cut[:0x0C] + (len(cut) - 0x54).to_bytes(4, "little") + cut[0x10:]

    with pytest.raises(BadImage, match="past the image end"):
        profile_image.decode(cut)


def test_it_rejects_profile_numbers_with_a_gap():
    image = build_image([*profile_records(1, "Office", []), *profile_records(3, "Racing Sim", [])])

    with pytest.raises(BadImage, match="expected 1 to 2"):
        profile_image.decode(image)
