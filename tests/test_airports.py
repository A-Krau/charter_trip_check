from app.airports import AirportIndex

idx = AirportIndex()


def test_lookup_by_icao_iata_and_faa():
    assert idx.get("KTEB").name.startswith("Teterboro")
    assert idx.get("teb").code == "KTEB"
    assert idx.get("JFK").code == "KJFK"
    assert idx.get("EGLL").iata == "LHR"


def test_search_prefers_exact_code():
    hits = idx.search("KTEB")
    assert hits[0].code == "KTEB"
    assert idx.search("Teterboro")[0].code == "KTEB"
