from glossary import extract_details, extract_tags


def test_random_one_attribute_absorb():
    text = "1ターン：ランダム1属性吸収"
    assert "Attribute absorb" in extract_tags(text)
    assert "1 random color" in extract_details(text)


def test_random_one_colour_absorb():
    text = "1ターン：ランダム1色吸収"
    assert "Attribute absorb" in extract_tags(text)
    assert "1 random color" in extract_details(text)


def test_random_two_attribute_absorb():
    assert "2 random colors" in extract_details("ランダム2属性吸収")


def test_plain_colour_absorb_not_random():
    assert not any("random" in d for d in extract_details("[光][闇]吸収"))
