from shared.services.taxi_router.readback_parser import (
    extract_taxiway_tokens,
    parse_pushback_direction,
)

# ---- extract_taxiway_tokens -------------------------------------------------


def test_structured_taxi_route_letters():
    got = extract_taxiway_tokens("Bravo, Delta, Echo")
    assert got == ["B", "D", "E"]


def test_structured_taxi_route_with_and():
    assert extract_taxiway_tokens("Bravo and Delta and Echo") == ["B", "D", "E"]


def test_fallback_from_instruction_text():
    text = "Iberia 3421, pushback approved face north, taxi via Bravo Delta Echo, holding short runway 06R, wilco."
    # No structured route provided -> parser scans the full phrase
    got = extract_taxiway_tokens(None, fallback_text=text)
    # The parser should capture the via taxiways (plus any extra capitalised
    # tokens it can resolve). We only require the three via points to appear
    # in order.
    for expected in ("B", "D", "E"):
        assert expected in got, got
    assert got.index("B") < got.index("D") < got.index("E")


def test_numeric_suffix_from_words():
    # "Golf one zero" -> "G10"
    assert extract_taxiway_tokens("Golf one zero, Hotel") == ["G10", "H"]


def test_numeric_suffix_from_digits():
    assert extract_taxiway_tokens("Delta 5, Foxtrot") == ["D5", "F"]


def test_known_tokens_filter():
    # Pilot says "Z" which isn't a real taxiway -- filtered out
    got = extract_taxiway_tokens("Bravo, Zulu", known_tokens=["B", "D"])
    assert got == ["B"]


def test_dedup_preserves_first_occurrence():
    assert extract_taxiway_tokens("Bravo, Bravo, Delta") == ["B", "D"]


def test_empty_inputs():
    assert extract_taxiway_tokens(None) == []
    assert extract_taxiway_tokens("") == []
    assert extract_taxiway_tokens("   ") == []


# ---- dedup=False (strict-routing path, issue #68) ---------------------------


def test_no_dedup_preserves_non_adjacent_repeat():
    got = extract_taxiway_tokens(
        "via alpha bravo alpha",
        known_tokens=["A", "B"],
        dedup=False,
    )
    assert got == ["A", "B", "A"]


def test_no_dedup_collapses_consecutive_stutter():
    # "alpha alpha bravo" is phonetic repetition, not a route revisit
    assert extract_taxiway_tokens("alpha alpha bravo", dedup=False) == ["A", "B"]


def test_no_dedup_known_tokens_filter_still_applies():
    got = extract_taxiway_tokens(
        "Bravo, Zulu, Bravo",
        known_tokens=["B", "D"],
        dedup=False,
    )
    # After Zulu is filtered the two Bravos become consecutive -> collapse
    assert got == ["B"]


def test_no_dedup_numeric_suffix_repeat():
    assert extract_taxiway_tokens("Golf one zero, Hotel, Golf one zero", dedup=False) == ["G10", "H", "G10"]


# ---- parse_pushback_direction ----------------------------------------------


def test_cardinal_directions():
    assert parse_pushback_direction("pushback approved face north") == 0.0
    assert parse_pushback_direction("face EAST") == 90.0
    assert parse_pushback_direction("facing south") == 180.0
    assert parse_pushback_direction("face the west") == 270.0


def test_intercardinal():
    assert parse_pushback_direction("face southwest") == 225.0
    assert parse_pushback_direction("face south-west") == 225.0


def test_numeric_heading():
    assert parse_pushback_direction("pushback face 090") == 90.0
    assert parse_pushback_direction("facing 360 degrees") == 0.0


def test_unknown_returns_none():
    assert parse_pushback_direction("pushback approved") is None
    assert parse_pushback_direction(None) is None
    assert parse_pushback_direction("") is None
