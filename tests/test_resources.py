"""resources.plan must tolerate GGUF metadata stored as per-layer arrays."""
from app import resources


def test_plan_handles_array_metadata(tmp_path, monkeypatch):
    model = tmp_path / "m.gguf"
    model.write_bytes(b"\0" * 1024)
    meta = {"block_count": 48, "context_length": 131072, "embedding_length": 3840,
            "attention.head_count": None, "attention.head_count_kv": None}
    monkeypatch.setattr(resources, "gguf_meta", lambda p: meta)
    monkeypatch.setattr(resources, "free_vram", lambda: 0)
    plan = resources.plan(model, want_ctx=4096)
    assert plan.n_ctx >= 512
    assert plan.n_gpu_layers == 0
