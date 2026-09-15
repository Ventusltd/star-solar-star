"""Expected bytes/seeds computed by the production Python contract."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from star_contract import JCS_CANONICALIZATION, observation_bytes, seed_for, validate


def vectors():
    base = json.loads((ROOT / "stars/global-solar-2025.star.json").read_text())
    cases = []
    for name, keys, values in [
        ("mixed case", ["a", "A", "z", "Z"], [1.0, -0.0, 0, 1.5]),
        ("unicode ordering", ["\ue000", "\U0001f600", "\u00e9", "e\u0301"], [1, 2, 3, 4]),
        ("fraction exponents", ["a", "b", "c", "d", "e"], [1e-6, 1e-7, 0.0000010000000000000002, 5e-324, 333333333.3333333]),
        ("safe bounds", ["a", "b", "c"], [9007199254740991, -9007199254740991, 1.2345678901234567]),
    ]:
        star = copy.deepcopy(base)
        star["observations"] = []
        for key, value in zip(keys, values):
            row = copy.deepcopy(base["observations"][0])
            row.update(key=key, value=value)
            row["metadata"] = {"\ue000": "BMP", "\U0001f600": "non-BMP", "A": "\t\n\"\\", "a": True}
            star["observations"].append(row)
        for variant in ("ordered", "reversed"):
            if variant == "reversed":
                star["observations"] = [dict(reversed(list(row.items()))) for row in reversed(star["observations"])]
            star["seed"] = {"algorithm": "sha256", "canonicalization": JCS_CANONICALIZATION,
                            "inputs": sorted(keys, key=lambda key: key.encode("utf-16be")), "url_parameter": "seed",
                            "value": seed_for(star["observations"], JCS_CANONICALIZATION)}
            validate(star)
            cases.append({"name": name + "/" + variant, "star": copy.deepcopy(star),
                          "bytes": observation_bytes(star["observations"], JCS_CANONICALIZATION).decode()})
    return cases


if __name__ == "__main__":
    print(json.dumps(vectors(), ensure_ascii=True))
