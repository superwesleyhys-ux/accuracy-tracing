"""Download one pinned GGUF model; inference itself never downloads or calls APIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

MODEL_REPOSITORY = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
MODEL_REVISION = "a06e946bb6b655725eafa393f4a9745d460374c9"
MODEL_FILENAME = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_SHA256 = "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
MODEL_BYTES = 2497281120


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def setup(model_dir, config_path):
    directory = Path(model_dir).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MODEL_FILENAME
    if not path.exists():
        temporary = path.with_suffix(".gguf.part")
        url = (f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/"
               f"{MODEL_REVISION}/{MODEL_FILENAME}")
        digest = hashlib.sha256()
        total = 0
        next_update = 250_000_000
        with urllib.request.urlopen(url, timeout=45) as response, temporary.open("wb") as stream:
            while chunk := response.read(4 * 1024 * 1024):
                stream.write(chunk)
                digest.update(chunk)
                total += len(chunk)
                if total >= next_update:
                    print(f"Downloaded {total / 1e9:.2f}/{MODEL_BYTES / 1e9:.2f} GB", flush=True)
                    next_update += 250_000_000
        if total != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
            raise ValueError("Model size/checksum mismatch; unverified download was not installed")
        temporary.replace(path)
    elif path.stat().st_size != MODEL_BYTES or file_sha256(path) != MODEL_SHA256:
        raise ValueError("Existing model checksum mismatch; file was not overwritten")
    config = {
        "backend": "llama_cpp_local_process",
        "model_path": os.path.relpath(path, config_path.parent),
        "model_sha256": MODEL_SHA256,
        "model_repository": MODEL_REPOSITORY,
        "model_revision": MODEL_REVISION,
        "context_tokens": 16384,
        "threads": min(8, os.cpu_count() or 1),
        "gpu_layers": 0,
        "seed": 0,
        "call_timeout_seconds": 240,
        "cloud_fallback": False,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Verified model: {path}", flush=True)
    print(f"Local configuration: {config_path}", flush=True)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", default=".models")
    parser.add_argument("--config", default=".local/model.json")
    args = parser.parse_args()
    try:
        setup(args.model_dir, args.config)
    except (OSError, ValueError) as exc:
        print(f"Local model setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
