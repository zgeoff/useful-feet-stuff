import pytest

from pedals.device import Device, Version
from pedals.hid import NoAnswer
from pedals.test_utils.fake_device import FakeDevice


def setup_test(fake: FakeDevice):
    return {"fake": fake, "device": Device(fake)}


def test_version_returns_the_text_of_a_new_style_answer():
    ctx = setup_test(FakeDevice())

    assert ctx["device"].version() == Version(text="Sep 26 2020 14:06:10 Ver 1.0.8", new_style=True)


def test_version_flags_an_old_style_answer():
    ctx = setup_test(FakeDevice(new_style=False))

    assert ctx["device"].version() == Version(text="Sep 26 2020 14:06:10 Ver 1.0.8", new_style=False)


def test_active_profile_returns_the_profile_number():
    ctx = setup_test(FakeDevice(active=3))

    assert ctx["device"].active_profile() == 3


def test_read_selects_the_space_and_joins_chunks_of_at_most_62_bytes():
    ctx = setup_test(FakeDevice(spaces={3: bytes(range(200))}))

    data = ctx["device"].read(space=3, addr=10, length=130)

    assert (data, ctx["fake"].sent) == (
        bytes(range(10, 140)),
        [
            bytes([0x0D, 0x01, 0x03]),
            bytes([0x02, 0x06, 62, 0, 10, 0, 0, 0]),
            bytes([0x02, 0x06, 62, 0, 72, 0, 0, 0]),
            bytes([0x02, 0x06, 6, 0, 134, 0, 0, 0]),
        ],
    )


@pytest.mark.parametrize("space", [0, 1, 0x81])
def test_read_refuses_space(space):
    ctx = setup_test(FakeDevice())

    with pytest.raises(ValueError, match="not readable"):
        ctx["device"].read(space=space, addr=0, length=1)


def test_read_raises_no_answer_when_the_device_returns_no_data():
    ctx = setup_test(FakeDevice(spaces={2: b""}))

    with pytest.raises(NoAnswer, match="no data"):
        ctx["device"].read(space=2, addr=0, length=4)


def test_version_raises_no_answer_from_a_silent_device():
    ctx = setup_test(FakeDevice(silent=True))

    with pytest.raises(NoAnswer):
        ctx["device"].version()


def test_switch_profile_sends_the_switch_command():
    ctx = setup_test(FakeDevice())

    ctx["device"].switch_profile(2)

    assert ctx["fake"].sent == [bytes([0x04, 0x01, 0x02])]
