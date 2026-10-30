import math

from shadowcost.shadow import compare, values_match


def test_numbers_match_within_tolerance():
    assert values_match(19.999999, 20)
    assert values_match(100.004, 100.0)
    assert not values_match(100.01, 100.0)


def test_strings_ignore_case_and_whitespace():
    assert values_match("  Paid ", "paid")
    assert not values_match("paid", "unpaid")


def test_missing_values_are_equivalent():
    assert values_match(None, "")
    assert values_match(math.nan, None)
    assert not values_match(None, 0)


def test_bool_is_not_treated_as_number():
    assert not values_match(True, 1)


def test_compare_flags_extra_and_missing_fields():
    agent = {"amount": 50, "status": "paid", "note": "x"}
    human = {"amount": 50, "status": "Paid"}
    result = compare(agent, human)
    assert result.field_matches == {"amount": True, "note": False, "status": True}
    assert not result.agrees
    assert result.mismatched_fields == ["note"]
    assert math.isclose(result.score, 2 / 3)


def test_compare_restricted_to_fields():
    result = compare({"amount": 50, "note": "x"}, {"amount": 50}, fields=["amount"])
    assert result.agrees
    assert result.score == 1.0
