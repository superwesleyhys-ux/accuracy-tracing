"""Inspect the real CLI request at a loopback stub; never invoke a remote model.

Run from the repository root. The stub returns HTTP 400 deliberately, so the
transport should report failure after the request has been inspected. Only
sanitized metadata is written; prompts and HTTP headers remain in memory.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import newsverify.tunnels as tunnels


def main():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((json.loads(body), "Authorization" in self.headers, self.path))
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Local inspection complete; no model invoked"}}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    saved_process, saved_discovery = tunnels.subprocess, tunnels._local_skill_paths
    profile = ["-c", 'model_provider="isolation_audit"', "-c",
               f'model_providers.isolation_audit={{name="Local no-inference capture",'
               f'base_url="http://127.0.0.1:{server.server_port}/v1",wire_api="responses",'
               'requires_openai_auth=false,supports_websockets=false,request_max_retries=0,stream_max_retries=0}']

    class CaptureProcess:
        def __getattr__(self, name):
            return getattr(subprocess, name)

        def run(self, command, *args, **kwargs):
            command = list(command)
            command[-1:-1] = profile
            return subprocess.run(command, *args, **kwargs)

    cases = []
    try:
        tunnels.subprocess = CaptureProcess()
        for condition in ("without_skill_override", "with_skill_override"):
            requests.clear()
            tunnels._local_skill_paths = (lambda env: ()) if condition == "without_skill_override" else saved_discovery
            transport = tunnels.LocalTunnel("gpt-6-astra", "medium", timeout=30)
            failed_as_expected = False
            try:
                transport.generate("isolation_probe", "Return JSON from the supplied packet only.",
                                   {"probe": True}, {"type": "object", "properties": {"probe": {"type": "boolean"}},
                                                    "required": ["probe"], "additionalProperties": False})
            except tunnels.TunnelError:
                failed_as_expected = True
            assert len(requests) == 1, "Expected exactly one loopback request"
            body, authorization, path = requests[0]
            rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
            inputs = json.dumps(body.get("input", []), ensure_ascii=False, sort_keys=True)
            row = {"condition": condition, "captured_requests": len(requests),
                   "requested_model": body.get("model"), "request_path": path,
                   "authorization_header_present": authorization,
                   "expected_stub_failure": failed_as_expected,
                   "installed_gstack_present": "gstack" in rendered,
                   "skill_catalog_present": "<skills_instructions>" in rendered,
                   "request_tools": body.get("tools", []),
                   "input_characters": len(inputs),
                   "rendered_input_sha256": hashlib.sha256(inputs.encode()).hexdigest(),
                   "disabled_skill_count": transport.calls[0].get("local_skills_disabled"),
                   "input_roles": [item.get("role") for item in body.get("input", []) if "role" in item]}
            assert not authorization and failed_as_expected and row["request_tools"] == []
            cases.append(row)
        assert cases[0]["installed_gstack_present"] and cases[0]["skill_catalog_present"], "Control did not reproduce the installed-skill exposure"
        assert not cases[1]["installed_gstack_present"] and not cases[1]["skill_catalog_present"], "Local skill isolation did not remove the installed catalog"
    finally:
        tunnels.subprocess, tunnels._local_skill_paths = saved_process, saved_discovery
        server.shutdown()
        server.server_close()

    output = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "cli_version": subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip(),
              "remote_model_invocations": 0,
              "method": "Actual LocalTunnel command and Codex exec request, with only the provider redirected to an unauthenticated loopback HTTP stub returning 400.",
              "shared_flags": ["--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--sandbox read-only", "-C temporary-directory", "web_search=disabled", "shell_tool=false", "apps=false", "plugins=false", "multi_agent=false"],
              "fix": "Explicit per-process skills.config entries with enabled=false; no installed skill, authentication file or user configuration was changed.",
              "notes": ["Disabling skill_search and enabling skip_host_skill_discovery did not remove the catalog in a separate prompt-input check.",
                        "Normal built-in Codex system and developer instructions remain. This is a skill-free local CLI baseline, not a raw base-model API request.",
                        "The control uses an empty skills.config override, which still loads installed skills like the original command.",
                        "Request contents and authorization values were not saved; only metadata and hashes are retained."],
              "files_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT / "newsverify/tunnels.py", ROOT / "tests/test_tunnels.py", Path(__file__)]},
              "cases": cases, "passed": True}
    destination = Path(__file__).with_name("ISOLATION_REVIEW.json")
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": True, "remote_model_invocations": 0, "cases": cases}, indent=2))


if __name__ == "__main__":
    main()
