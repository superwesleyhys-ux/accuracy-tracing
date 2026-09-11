import unittest

from newsverify.early_risk import build_packet, run_early_risk


def case(target_text="The source reports seven."):
    return {
        "target": {"id": "fixture", "text": target_text,
                   "as_of": "2023-12-31T23:59:59Z", "source_version_id": "v1"},
        "materials": [
            {"version_id": "v1", "url": "https://example.invalid/paper", "issuer": "Paper; excerpt",
             "available_at": "2023-01-01T00:00:00Z", "availability_basis": "Archived in 2023.",
             "content": "Source header. The source reports seven. It says the samples followed method A."},
            {"version_id": "v2", "url": "https://example.invalid/paper", "issuer": "Paper; full text",
             "available_at": "2023-01-01T00:00:00Z", "availability_basis": "Same archived paper.",
             "content": "The same publication in full."},
            {"version_id": "future", "url": "https://example.invalid/future", "issuer": "Later notice",
             "available_at": "2025-01-01T00:00:00Z", "availability_basis": "Published later.",
             "content": "SECRET FUTURE FINDING"},
        ],
    }


class FakeTransport:
    kind = "local"
    model = "fixture-model"
    reasoning_effort = "low"

    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate(self, stage, instructions, packet, schema):
        self.calls.append({"stage": stage, "success": True,
                           "usage": {"input_tokens": 100, "output_tokens": 20}})
        self.packet = packet
        return self.result


class EarlyRiskTests(unittest.TestCase):
    def test_packet_uses_origin_and_excludes_post_cutoff_material(self):
        packet, passages = build_packet(case())
        self.assertEqual({"v1"}, {p.version_id for p in passages.values()})
        serialized = repr(packet)
        self.assertNotIn("SECRET FUTURE FINDING", serialized)
        self.assertNotIn("future", {row["version_id"] for row in packet["source_inventory"]})

    def test_supported_attribution_gets_program_owned_exact_offsets(self):
        packet, passages = build_packet(case())
        passage_id = next(pid for pid, p in passages.items() if "reports seven" in p.text)
        transport = FakeTransport({
            "claim_scope": "source_attribution", "fact_verdict": "supported",
            "evidence_passage_ids": [passage_id], "independent_authentication": False,
            "fraud_risk": "low", "risk_signals": [], "rationale": "The source says this.",
        })
        result = run_early_risk(case(), transport=transport)
        evidence = result["evidence"][0]
        content = case()["materials"][0]["content"]
        self.assertEqual(evidence["quote"], content[evidence["start"]:evidence["end"]])
        self.assertEqual(1, len(result["calls"]))

    def test_risk_cannot_replace_unresolved_factual_verdict(self):
        transport = FakeTransport({
            "claim_scope": "real_world_provenance", "fact_verdict": "contradicted",
            "evidence_passage_ids": ["p001"], "independent_authentication": False,
            "fraud_risk": "high", "risk_signals": ["self-attestation"],
            "rationale": "High risk is not proof.",
        })
        with self.assertRaisesRegex(ValueError, "must remain unresolved"):
            run_early_risk(case("The samples actually came from method A."), transport=transport)

    def test_unknown_passage_id_fails_closed(self):
        transport = FakeTransport({
            "claim_scope": "source_attribution", "fact_verdict": "supported",
            "evidence_passage_ids": ["p999"], "independent_authentication": False,
            "fraud_risk": "low", "risk_signals": [], "rationale": "Citation supplied.",
        })
        with self.assertRaisesRegex(ValueError, "unavailable passage"):
            run_early_risk(case(), transport=transport)


if __name__ == "__main__":
    unittest.main()
