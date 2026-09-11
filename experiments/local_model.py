"""Direct local llama.cpp inference in a bounded worker; no HTTP or cloud fallback."""
from copy import deepcopy
import hashlib
import json
import multiprocessing
from pathlib import Path
import socket
import time
from types import SimpleNamespace


def _deny_network(*args, **kwargs):
    raise RuntimeError("Network access is disabled in the local inference worker")


def sampling_schema(value):
    """Avoid exponential grammar expansion; full bounds remain in Python gates.

    llama.cpp expands bounded strings/arrays into repetitions. Nested stage
    schemas can exceed its grammar limits. Only the sampling grammar omits
    those bounds; the model sees the original schema and the existing staged
    validators still check every original length/cardinality bound.
    """
    if isinstance(value, dict):
        return {key: sampling_schema(child) for key, child in value.items()
                if key not in {"minLength", "maxLength", "minItems", "maxItems"}}
    if isinstance(value, list):
        return [sampling_schema(child) for child in value]
    return value


def scoped_sampling_schema(schema, messages):
    """Limit source references to the actual layer input, never target metadata.

    These constraints narrow decoding only. They do not create evidence or
    replace the existing staged schema, quote, scope, and grounding gates.
    """
    result = sampling_schema(schema)
    try:
        payload = json.loads(messages[-1]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return result
    if not isinstance(payload, dict) or not isinstance(payload.get("materials"), list):
        return result
    versions = sorted({item["version_id"] for item in payload["materials"]})

    def constrain(node):
        if not isinstance(node, dict):
            return
        properties = node.get("properties", {})
        if node.get("type") == "array":
            item_properties = node.get("items", {}).get("properties", {})
            if {"version_id", "quote"} <= item_properties.keys():
                if versions:
                    item_properties["version_id"]["enum"] = versions
                else:
                    # A zero-length array has a small, bounded grammar.
                    node["maxItems"] = 0
        if {"dimension", "verdict", "basis_indices"} <= properties.keys():
            if not versions or payload.get("missing_scope"):
                properties["verdict"]["enum"] = ["unresolved"]
            if not versions:
                properties["basis_indices"]["maxItems"] = 0
        for child in node.values():
            if isinstance(child, dict):
                constrain(child)
            elif isinstance(child, list):
                for item in child:
                    constrain(item)
    constrain(result)
    return result


def _worker(pipe, config):
    # The pipe already exists. Inference cannot create a network connection,
    # even if a future dependency were to try to download or contact a service.
    try:
        from llama_cpp import Llama
        socket.socket = _deny_network
        socket.create_connection = _deny_network
        llm = Llama(
            model_path=config["model_path"], n_ctx=config["context_tokens"],
            n_threads=config["threads"], n_threads_batch=config["threads"],
            n_gpu_layers=config["gpu_layers"], seed=config["seed"],
            n_batch=512, chat_format="chatml", verbose=False)
        pipe.send({"ready": True})
        while True:
            request = pipe.recv()
            if request is None:
                break
            try:
                pipe.send({"response": llm.create_chat_completion(**request)})
            except Exception as exc:
                pipe.send({"error_type": type(exc).__name__, "error": str(exc)})
        llm.close()
    except Exception as exc:
        pipe.send({"error_type": type(exc).__name__, "error": str(exc)})
    finally:
        pipe.close()


def load_config(path):
    path = Path(path).expanduser().absolute()
    config = json.loads(path.read_text())
    if config.get("backend") != "llama_cpp_local_process":
        raise ValueError("Local inference requires backend=llama_cpp_local_process")
    if config.get("cloud_fallback") is not False:
        raise ValueError("Local inference requires cloud_fallback=false")
    model = (path.parent / config["model_path"]).absolute()
    if not model.is_file():
        raise FileNotFoundError("Local GGUF model is missing; run setup_local_model.py")
    with model.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_hash != config.get("model_sha256"):
        raise ValueError("Local model checksum mismatch")
    for name in ("context_tokens", "threads", "call_timeout_seconds"):
        if type(config.get(name)) is not int or config[name] < 1:
            raise ValueError(name + " must be a positive integer")
    if type(config.get("seed")) is not int or type(config.get("gpu_layers")) is not int:
        raise ValueError("seed and gpu_layers must be integers")
    return {**config, "model_path": str(model)}


class LocalTransport:
    """Translate the existing client contract to a local process, never a URL."""
    def __init__(self, config_path):
        self.config = load_config(config_path)
        self.model_id = "local/" + Path(self.config["model_path"]).stem
        self.records = []
        context = multiprocessing.get_context("spawn")
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child, self.config), daemon=True)
        self.process.start()
        child.close()
        if not self.pipe.poll(90):
            self.close()
            raise TimeoutError("Local model loading timed out")
        ready = self.pipe.recv()
        if ready.get("ready") is not True:
            self.close()
            raise RuntimeError("Local model loading failed: " + ready.get("error", "unknown"))

    def __call__(self, **kwargs):
        if not self.process.is_alive():
            raise RuntimeError("Local worker is unavailable; cloud fallback is disabled")
        if kwargs.get("model") != self.model_id:
            raise ValueError("Requested model differs from the loaded local model")
        if kwargs.get("reasoning_effort"):
            raise ValueError("reasoning_effort is not a supported local sampling setting")
        messages = deepcopy(kwargs["messages"])
        response_format = kwargs.get("response_format")
        local_format = None
        if response_format:
            local_format = {"type": "json_object"}
            if response_format["type"] == "json_schema":
                schema = response_format["json_schema"]["schema"]
                local_format["schema"] = scoped_sampling_schema(schema, messages)
                messages[0]["content"] += (
                    "\nReturn only JSON matching this exact schema; keep strings concise:\n"
                    + json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
                messages[0]["content"] += (
                    "\nUse empty notes unless an essential ambiguity needs recording. "
                    "Each rationale should be one short sentence. "
                    "If the schema has citations, these are references to OTHER sources "
                    "explicitly identifiable in the source BODY, not the current material's "
                    "own URL from metadata and not a list of its factual claims. "
                    "A metadata URL is never source-side citation evidence. "
                    "When no external reference is visible, return citations: []. "
                    "The origin field may still identify the current original record.")
                if "probe_results" in schema.get("properties", {}):
                    messages[0]["content"] += (
                        "\nFor verification layers, only materials contains admissible evidence; "
                        "the target and its source_version_id are not evidence. "
                        "With materials=[], use basis_pool=[], basis_indices=[], and unresolved "
                        "for every required dimension. With missing_scope nonempty, use gaps=[] "
                        "and stop_reason=scope_unavailable; the program retrieves those versions. "
                        "Do not invent extra target qualifiers: scope_location concerns the scope "
                        "stated in the target, not an unstated geographic location.")
        request = {"messages": messages, "model": self.model_id,
                   "temperature": 0.0, "seed": self.config["seed"],
                   "max_tokens": kwargs["max_completion_tokens"],
                   "response_format": local_format, "stream": False}
        record = {"request": request, "status": "running"}
        self.records.append(record)
        started = time.monotonic()
        self.pipe.send(request)
        timeout = min(float(kwargs["timeout"]), self.config["call_timeout_seconds"])
        if not self.pipe.poll(max(0, timeout)):
            record.update(status="error", error_type="TimeoutError", seconds=time.monotonic() - started)
            self.close()
            raise TimeoutError("Local inference deadline exceeded; worker stopped")
        try:
            result = self.pipe.recv()
        except (EOFError, OSError) as exc:
            record.update(status="error", error_type=type(exc).__name__,
                          error="Local worker exited before returning a response",
                          seconds=time.monotonic() - started)
            self.close()
            raise RuntimeError("Local worker exited; cloud fallback is disabled") from None
        record["seconds"] = time.monotonic() - started
        if "response" not in result:
            record.update(status="error", **result)
            raise RuntimeError("Local inference failed: " + result.get("error", "unknown"))
        value = result["response"]
        record.update(status="completed", response=value)
        return SimpleNamespace(
            id=value["id"], model=self.model_id,
            usage=SimpleNamespace(**value["usage"]),
            choices=[SimpleNamespace(
                finish_reason=choice["finish_reason"],
                message=SimpleNamespace(**choice["message"])) for choice in value["choices"]])

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=5)
        self.pipe.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
