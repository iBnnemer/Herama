import time

from app import monitor


def test_parse_gpu_line():
    out = "NVIDIA GeForce RTX 3080 Ti, 12, 912, 12288, 56, 28.5, 350.00, 4, 16\n"
    g = monitor.parse_gpu(out)
    assert g["name"] == "NVIDIA GeForce RTX 3080 Ti"
    assert g["vram_used_mb"] == 912 and g["vram_total_mb"] == 12288
    assert g["power_limit"] == 350.0 and g["pcie_gen"] == 4 and g["pcie_width"] == 16


def test_parse_gpu_bad_output():
    assert monitor.parse_gpu("") == {}
    assert monitor.parse_gpu("garbage") == {}


def test_state_flow_and_request_record():
    monitor.set_state("queued", "Loading x")
    assert monitor.state()["state"] == "queued"
    monitor.progress(50, 100)
    assert monitor.state()["state"] == "reading" and monitor.state()["progress"] == 0.5
    monitor.generating(40.0)
    assert monitor.state()["state"] == "generating" and monitor.state()["tps"] == 40.0
    monitor.finish("done", prompt=100, reused=60, output=20, decode_tps=41.0, prefill_tps=900.0, duration=1.5)
    assert monitor.state()["state"] == "idle"
    snap = monitor.snapshot(ctx_total=4096)
    r = snap["requests"][0]
    assert r["prompt"] == 100 and r["reused"] == 60 and r["hit_rate"] == 0.6 and r["output"] == 20
    assert snap["ctx_used"] == 120 and snap["decode_tps"] == 41.0 and snap["ctx_total"] == 4096


def test_error_stays_then_expires(monkeypatch):
    monitor.fail("boom")
    monitor.finish("done", 1, 0, 1, 1.0, 1.0, 0.1)
    assert monitor.state()["state"] == "error"
    monkeypatch.setattr(monitor, "ERROR_SHOW_SECONDS", -1)
    assert monitor.state()["state"] == "idle"
