from shared.services.taxi_router.constraints import merge_constraints


def test_empty_inputs():
    assert merge_constraints([], []) == []
    assert merge_constraints(["B"], []) == ["B"]
    assert merge_constraints([], ["B"]) == ["B"]


def test_pilot_readback_matches_controller():
    assert merge_constraints(["B", "D", "E"], ["B", "D", "E"]) == ["B", "D", "E"]


def test_pilot_missed_token_gets_inserted():
    # Controller: B,D,E — pilot only read "B,D" → E appended
    assert merge_constraints(["B", "D", "E"], ["B", "D"]) == ["B", "D", "E"]


def test_pilot_missed_middle_token():
    # Controller: B,D,E — pilot read "B,E" → D inserted after B
    assert merge_constraints(["B", "D", "E"], ["B", "E"]) == ["B", "D", "E"]


def test_pilot_added_extra_token_preserved():
    # Pilot adds Z; controller "E" still ends up in order
    assert merge_constraints(["B", "E"], ["B", "Z", "E"]) == ["B", "Z", "E"]


def test_pilot_reordered_takes_precedence():
    # Pilot order wins; controller tokens not mentioned go to the end
    assert merge_constraints(["B", "D", "E"], ["D", "B"]) == ["D", "B", "E"]


def test_case_insensitive_and_dedup():
    assert merge_constraints(["b", "B", "d"], ["B", "D"]) == ["B", "D"]


def test_all_controller_tokens_missing_appended_in_order():
    assert merge_constraints(["B", "D", "E"], ["Z"]) == ["Z", "B", "D", "E"]
