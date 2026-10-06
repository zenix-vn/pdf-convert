import pytest

from zenix_pdf.core.page_range import parse_page_range


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("", None),
        ("   ", None),
        ("1", [0]),
        ("1-3", [0, 1, 2]),
        ("1-3, 5", [0, 1, 2, 4]),
        (" 2 - 4 ", [1, 2, 3]),
        ("5, 1-2, 2", [0, 1, 4]),
        ("1,,3", [0, 2]),
        ("10", [9]),
    ],
)
def test_valid(spec, expected):
    assert parse_page_range(spec, 10) == expected


@pytest.mark.parametrize("spec", ["0", "5-3", "11", "1-11", "abc", "1-2-3", "-2", ",", "1;2"])
def test_invalid(spec):
    with pytest.raises(ValueError):
        parse_page_range(spec, 10)
