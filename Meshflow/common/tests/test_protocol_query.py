import pytest

from common.protocol import Protocol, protocol_from_query_param


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("meshtastic", Protocol.MESHTASTIC),
        ("meshcore", Protocol.MESHCORE),
        ("2", Protocol.MESHCORE),
        ("bogus", None),
    ],
)
def test_protocol_from_query_param(raw, expected):
    assert protocol_from_query_param(raw) == expected
