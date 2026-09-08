"""Local inference configuration, transport and failure isolation without model weights."""
from argparse import Namespace
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import local_inference
import local_model


class LocalModelTests(unittest.TestCase):
    def config(self, directory):
        model = Path(directory) / "weights.gguf"
        model.write_bytes(b"test weights; never loaded by these tests")
        path = Path(directory) / "config.json"
        value = {"backend": "llama_cpp_local_process", "model_path": "weights.gguf",
                 "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                 "context_tokens": 8192, "threads": 2, "seed": 0, "gpu_layers": 0,
                 "call_timeout_seconds": 10, "cloud_fallback": False}
        path.write_text(json.dumps(value))
        return path, value, model

    def transport(self, available=True):
        transport = local_model.LocalTransport.__new__(local_model.LocalTransport)
        transport.config = {"seed": 0, "call_timeout_seconds": 10}
        transport.model_id = "local/test"
        transport.records = []
        transport.process = Mock()
        transport.process.is_alive.return_value = True
        transport.pipe = Mock()
        transport.pipe.poll.return_value = available
        transport.pipe.recv.return_value = {"response": {
            "id": "local-response", "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": '{"answer":true}'}}]}}
        return transport

    def request(self):
        return {"model": "local/test", "messages": [{"role": "system", "content": "Verify"},
                                                    {"role": "user", "content": "Evidence"}],
                "max_completion_tokens": 100, "timeout": 5,
                "response_format": {"type": "json_schema", "json_schema": {"schema": {
                    "type": "object", "properties": {"answer": {"type": "boolean"}},
                    "required": ["answer"], "additionalProperties": False}}}}

    def test_config_resolves_relative_weights_and_requires_exact_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _, model = self.config(tmp)
            self.assertEqual(str(model), local_model.load_config(path)["model_path"])
            model.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                local_model.load_config(path)

    def test_config_rejects_cloud_fallback_and_invalid_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, value, _ = self.config(tmp)
            for changed in [{"cloud_fallback": True}, {"backend": "openai"}, {"threads": 0}, {"call_timeout_seconds": False}]:
                path.write_text(json.dumps({**value, **changed}))
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    local_model.load_config(path)

    def test_schema_is_sent_to_local_worker_and_input_is_not_mutated(self):
        transport = self.transport()
        request = self.request()
        original = json.dumps(request)
        with patch("socket.create_connection", side_effect=AssertionError("HTTP forbidden")):
            response = transport(**request)
        sent = transport.pipe.send.call_args.args[0]
        self.assertEqual(request["response_format"]["json_schema"]["schema"], sent["response_format"]["schema"])
        self.assertIn('"answer"', sent["messages"][0]["content"])
        self.assertEqual(original, json.dumps(request))
        self.assertEqual(20, response.usage.prompt_tokens)
        self.assertEqual('{"answer":true}', response.choices[0].message.content)

    def test_timeout_terminates_local_worker_without_fallback(self):
        transport = self.transport(available=False)
        with self.assertRaises(TimeoutError):
            transport(**self.request())
        transport.process.terminate.assert_called_once()
        self.assertEqual("TimeoutError", transport.records[0]["error_type"])

    def test_sampling_limits_remain_in_original_prompt_and_python_gate(self):
        transport = self.transport()
        request = self.request()
        original = request["response_format"]["json_schema"]["schema"]
        original["properties"]["answer"] = {"type": "string", "maxLength": 2}
        transport(**request)
        sent = transport.pipe.send.call_args.args[0]
        self.assertNotIn("maxLength", sent["response_format"]["schema"]["properties"]["answer"])
        self.assertIn('"maxLength":2', sent["messages"][0]["content"])
        from staged_semantic import _validate
        with self.assertRaisesRegex(ValueError, "string length"):
            _validate({"answer": "too long"}, original)

    def test_wrong_model_does_not_send_request(self):
        transport = self.transport()
        with self.assertRaisesRegex(ValueError, "differs"):
            transport(**{**self.request(), "model": "cloud/model"})
        transport.pipe.send.assert_not_called()

    def test_scoped_decoder_rejects_target_source_as_layer_evidence(self):
        from prompt_specs import LAYER_CRITIC_SCHEMA
        from staged_semantic import _validate
        original = json.dumps(LAYER_CRITIC_SCHEMA)
        payload = {"target": {"source_version_id": "claim"},
                   "materials": [{"version_id": "outcome", "content": "Actual result."}]}
        schema = local_model.scoped_sampling_schema(
            LAYER_CRITIC_SCHEMA, [{"content": json.dumps(payload)}])
        answer = {"decision": "repair", "issue": "Check outcome.",
                  "basis": [{"version_id": "outcome", "quote": "Actual result."}]}
        _validate(answer, LAYER_CRITIC_SCHEMA)
        ref_schema = schema["properties"]["basis"]["items"]
        _validate(answer["basis"][0], ref_schema)
        answer["basis"][0]["version_id"] = "claim"
        with self.assertRaises(ValueError):
            _validate(answer["basis"][0], ref_schema)
        self.assertEqual(original, json.dumps(LAYER_CRITIC_SCHEMA))

    def test_empty_scope_decoder_cannot_invent_evidence_or_conclusion(self):
        from prompt_specs import LAYER_SCHEMA
        from staged_semantic import _validate
        schema = local_model.scoped_sampling_schema(LAYER_SCHEMA, [{"content": json.dumps({
            "target": {"source_version_id": "claim"}, "materials": [],
            "missing_scope": ["outcome"]})}])
        answer = {"probe_results": [{"probe_number": 1, "basis_pool": [],
            "dimension_results": [{"dimension": "actor_subject", "verdict": "unresolved",
                                   "basis_indices": [], "rationale": "Scoped material is missing."}],
            "gaps": [], "resolutions": [], "stop_reason": "scope_unavailable"}]}
        _validate(answer, LAYER_SCHEMA)
        result_schema = schema["properties"]["probe_results"]["items"]["properties"]
        verdict_schema = result_schema["dimension_results"]["items"]["properties"]["verdict"]
        result = answer["probe_results"][0]
        _validate("unresolved", verdict_schema)
        _validate([], result_schema["basis_pool"])
        with self.assertRaises(ValueError):
            _validate("supported", verdict_schema)
        result["basis_pool"] = [{"version_id": "claim", "quote": "Invented evidence."}]
        with self.assertRaises(ValueError):
            _validate(result["basis_pool"], result_schema["basis_pool"])

    def test_worker_disables_network_before_loading_and_generating(self):
        checks = []
        class FakeLlama:
            def __init__(self, **kwargs):
                with self_test.assertRaisesRegex(RuntimeError, "Network access"):
                    socket.socket()
                checks.append("load")
            def create_chat_completion(self, **kwargs):
                with self_test.assertRaisesRegex(RuntimeError, "Network access"):
                    socket.create_connection(("example.com", 443))
                checks.append("generate")
                return {"output": "local"}
            def close(self):
                checks.append("closed")
        self_test = self
        pipe = Mock()
        pipe.recv.side_effect = [{"messages": []}, None]
        config = {"model_path": "test", "context_tokens": 100, "threads": 1, "gpu_layers": 0, "seed": 0}
        with patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=FakeLlama)}), \
                patch.object(socket, "socket", socket.socket), \
                patch.object(socket, "create_connection", socket.create_connection):
            local_model._worker(pipe, config)
        self.assertEqual(["load", "generate", "closed"], checks)

    def test_missing_model_stays_local_and_writes_explicit_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(inputs=str(ROOT / "experiments/historical-2023-pilot2-v3/inputs.json"),
                             output=str(Path(tmp) / "run"), case=None, config="missing.json",
                             semantic_mode="staged", max_rounds=1, max_calls=20, case_seconds=60,
                             include_controls=False)
            with patch.object(local_inference, "LocalTransport", side_effect=FileNotFoundError("missing model")):
                self.assertEqual(1, local_inference.run(args))
            status = json.loads((Path(args.output) / "status.json").read_text())
            self.assertEqual("local_runtime_error", status["status"])
            self.assertEqual(0, status["cloud_api_calls"])
            self.assertFalse(status["fallback"])


if __name__ == "__main__":
    unittest.main()
