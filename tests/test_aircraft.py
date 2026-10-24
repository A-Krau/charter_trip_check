from app.aircraft import load_operators, operator_from_callsign, us_registration


def test_us_registration_known_values():
    assert us_registration("a00001") == "N1"
    assert us_registration("a00002") == "N1A"
    assert us_registration("a00003") == "N1AA"
    assert us_registration("adf7c7") == "N99999"


def test_us_registration_round_trip_is_unique():
    seen = set()
    for i in range(0xA00001, 0xA00001 + 120000, 7):
        n = us_registration(f"{i:06x}")
        assert n and n.startswith("N") and len(n) <= 6
        assert "I" not in n and "O" not in n
        seen.add(n)
    assert len(seen) == len(range(0xA00001, 0xA00001 + 120000, 7))


def test_us_registration_rejects_non_us():
    assert us_registration("4ca123") is None
    assert us_registration("zzzzzz") is None


def test_operator_from_callsign():
    ops = load_operators()
    assert operator_from_callsign("EJA512 ", ops) == "NetJets"
    assert operator_from_callsign("LXJ401", ops) == "Flexjet"
    assert operator_from_callsign("N123AB", ops) is None
