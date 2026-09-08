"""Read-only structural/evidence audit; human/agent semantic review is separate."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"
sys.path.insert(0, str(ROOT))
from newsverify.provenance import MaterialVersion, _material_eligibility, _time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    corpus = json.loads((DATA / "corpus.json").read_text())
    gold = json.loads((DATA / "gold.json").read_text())
    index = json.loads((DATA / "source_index.json").read_text())
    sources = {s["version_id"]: s for s in index["sources"]}
    cases = {c["target"]["id"]: c for c in corpus["cases"]}
    labels = {g["id"]: g for g in gold["cases"]}
    assert len(cases) == len(corpus["cases"]) == len(labels) == len(gold["cases"]) == 6
    assert set(cases) == set(labels)
    assert len({g["event_id"] for g in labels.values()}) == 3
    assert index["corpus_sha256"] == digest(DATA / "corpus.json")
    assert index["gold_sha256"] == digest(DATA / "gold.json")
    texts = {}
    for identifier, source in sources.items():
        for kind in ("raw", "text", "metadata"):
            assert digest(DATA / source[kind + "_path"]) == source[kind + "_sha256"]
        # Exported text files add one serialization newline after the packet text.
        texts[identifier] = (DATA / source["text_path"]).read_text().removesuffix("\n")
    checked = []
    for identifier, case in cases.items():
        assert set(case) == {"target", "initial_version_ids", "materials", "config"}
        assert set(case["target"]) == {"id", "text", "as_of", "source_version_id"}
        label = labels[identifier]
        assert case["target"]["text"] == label["claim"]
        materials = {m["version_id"]: m for m in case["materials"]}
        assert len(materials) == len(case["materials"])
        assert case["initial_version_ids"] == [case["target"]["source_version_id"]]
        assert set(case["initial_version_ids"]) <= set(materials)
        for vid, m in materials.items():
            assert not _material_eligibility(MaterialVersion(**m), _time(case["target"]["as_of"], "cutoff"))
            assert m["content"] == texts[vid] and m["url"] == sources[vid]["url"]
        for e in label["evidence"]:
            text = materials[e["version_id"]]["content"]
            assert text[e["start"]:e["end"]] == e["quote"]
            assert text.find(e["quote"]) == e["start"] and text.find(e["quote"], e["start"] + 1) < 0
        ref = label.get("withheld_reference_check")
        if ref:
            assert ref["reference_version_id"] not in materials
            assert ref["reference_quote"] in texts[ref["reference_version_id"]]
            assert all(ref["reference_quote"] not in m["content"] for m in materials.values())
        checked.append({"id": identifier, "gold_quote_count": len(label["evidence"]),
                        "eligible_pool": list(materials), "withheld_control": bool(ref)})
    assert "https://www.nature.com/articles/s41586-024-07378-0" in texts["s01"]
    assert "10.1103/PhysRevResearch.7.L012020" in texts["s03"]
    assert "10.1103/PhysRevResearch.7.L012020" in texts["s04"]
    assert "https://mcube.mit.edu/research/simPLE.html" in texts["s05"]
    return {"passed": True, "corpus_sha256": digest(DATA / "corpus.json"),
            "gold_sha256": digest(DATA / "gold.json"), "source_count": len(sources),
            "source_hashes_valid": True, "cases": checked}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
