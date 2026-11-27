import importlib


def test_left_and_right_parts_mapped():
    module = importlib.import_module("merge")
    maps = [v for v in vars(module).values() if isinstance(v, dict) and "聖鳥" in v]
    assert maps, "no part-name map found"
    assert maps[0]["左部位"] == "Left part"
    assert maps[0]["右部位"] == "Right part"
