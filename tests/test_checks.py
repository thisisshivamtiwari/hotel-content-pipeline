import copy

import pytest

from hotel_content import checks, llm

BRIEFS = checks.load_briefs()


@pytest.fixture
def good():
    return {
        "google_rsa": {
            "headlines": ["The Lantern Rooms", "Rooms from £79", "4 mins to Central", "Rainfall showers", "Free Wi-Fi"],
            "descriptions": [
                "20% off 2 nights or more, Sunday to Thursday. Book by 31 January 2027.",
                "Blackout blinds and a rainfall shower in all 24 rooms.",
                "Self check-in, staffed reception 7am to 11pm.",
            ],
        },
        "meta_ad": {
            "primary_text": "Quiet rooms 4 minutes from Pellingford Central. From £79 a night.",
            "headline": "Midweek in Pellingford",
        },
        "instagram": {"caption": "Blackout blinds, rainfall showers, 4 minutes from the station.", "hashtags": ["#Pellingford"]},
        "reel": {
            "scenes": [
                {"shot": "exterior_dusk", "on_screen_text": "The Lantern Rooms", "seconds": 4},
                {"shot": "room_wide", "on_screen_text": "Blackout blinds", "seconds": 4},
                {"shot": "shower_detail", "on_screen_text": "Rainfall shower", "seconds": 4},
                {"shot": "station_walk", "on_screen_text": "4 mins to the station", "seconds": 3},
            ],
            "voiceover": "Sleep in the dark, shower like it's summer, and walk to the station in 4 minutes.",
        },
        "image_post": {"headline": "Rooms from £79", "subline": "4 minutes from Pellingford Central"},
    }


def rules(pack, hid="lantern"):
    return sorted({i["rule"] for i in checks.check_pack(pack, BRIEFS[hid])})


def test_clean_pack_passes(good):
    assert checks.check_pack(good, BRIEFS["lantern"]) == []


def test_length_and_count(good):
    good["google_rsa"]["headlines"][0] = "A headline that is far too long for Google"
    good["google_rsa"]["descriptions"].pop()
    assert rules(good) == ["length", "shape"]


def test_unknown_number(good):
    good["meta_ad"]["primary_text"] = "Rooms from £69 a night."
    assert rules(good) == ["number"]


def test_unavailable_amenity_and_negation(good):
    good["instagram"]["caption"] = "Relax by the pool after a city day."
    assert rules(good) == ["unavailable"]
    good["instagram"]["caption"] = "No parking, no fuss: 4 minutes from the station."
    assert rules(good) == []


def test_superlative(good):
    good["image_post"]["subline"] = "The best rooms in Pellingford"
    assert rules(good) == ["superlative"]


def test_offer_needs_terms_in_same_unit(good):
    good["meta_ad"]["primary_text"] = "20% off midweek stays at The Lantern Rooms."
    issues = [i for i in checks.check_pack(good, BRIEFS["lantern"]) if i["rule"] == "offer-terms"]
    assert {i["field"] for i in issues} == {"meta_ad"} and len(issues) == 2
    good["meta_ad"]["primary_text"] = "20% off 2+ nights, Sun-Thu, at The Lantern Rooms."
    assert rules(good) == []


def test_footage_and_reel_timing(good):
    bad = copy.deepcopy(good)
    bad["reel"]["scenes"][0]["shot"] = "rooftop_pool"
    bad["reel"]["scenes"][1]["seconds"] = 1
    assert rules(bad) == ["footage", "shape"]


def test_hashtags(good):
    good["instagram"]["hashtags"] = ["#a", "#b", "#c", "#d", "#e", "#f"]
    assert rules(good) == ["shape"]
    good["instagram"]["hashtags"] = ["#city break"]
    assert rules(good) == ["shape"]


def test_not_a_pack():
    assert checks.check_pack(None, BRIEFS["lantern"])[0]["rule"] == "shape"


def test_every_brief_is_complete():
    for b in BRIEFS.values():
        assert {"facts", "prices", "offer", "not_available", "footage", "brand"} <= set(b)
        assert b["offer"]["trigger"] and b["offer"]["required"]
        assert all(isinstance(g, list) and g for g in b["offer"]["required"])


def test_parse_json_variants():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Here: [{"x": 2}] done') == [{"x": 2}]
    assert llm.parse_json("no json") is None
