"""Web UI: job views, state-specific actions and the HTTP API (no browser needed)."""

import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def server(settings, monkeypatch):
    from reelforge.web import server as web

    srv = web.make_server(settings, port=0)
    sent: list[list[str]] = []
    monkeypatch.setattr(srv.RequestHandlerClass.app.runner, "start", lambda args: sent.append(args))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, sent
    srv.shutdown()
    srv.server_close()


def call(base: str, path: str, body: dict | None = None, header: bool = True):
    req = urllib.request.Request(base + path)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
        if header:
            req.add_header("X-ReelForge", "1")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_web_shows_jobs_and_voice_actions(settings, script_file, server):
    from reelforge.jobs.orchestrator import Pipeline
    from reelforge.schemas import JobConfig

    base, sent = server
    job = Pipeline(settings, log=lambda m: None).create_from_script(
        script_file, JobConfig(voice_mode="ask", fetch_sources=False)
    )
    state = call(base, "/api/state")
    assert [j["id"] for j in state["jobs"]] == [job.id] and state["jobs"][0]["status"] == "Choose the voice"
    d = call(base, f"/api/jobs/{job.id}")
    labels = [a["label"] for a in d["next"]["actions"]]
    assert labels == ["Record Voice", "Use an audio file…", "Use AI voice"]
    assert d["step"] == 1 and not d["failed"]  # script done, voice is the current step
    assert d["script"]["kind"] == "script" and d["script"]["sections"][0]["role"] == "hook"
    ai = d["next"]["actions"][2]
    assert ai["args"] == ["voice", job.id, "--ai", "--yes"] and ai["confirm"]

    call(base, "/api/run", {"args": ai["args"]})
    assert sent[-1] == ["voice", job.id, "--ai", "--yes"]
    call(base, "/api/create", {"source": "topic", "topic": "Why AI struggles with hands", "preview_gate": False})
    assert sent[-1][:3] == ["create", "--topic", "Why AI struggles with hands"] and "--no-preview-gate" in sent[-1]


def test_web_draft_pick_and_guards(settings, server):
    from reelforge.jobs.orchestrator import Pipeline
    from reelforge.providers import FallbackLLM
    from reelforge.schemas import JobConfig
    from reelforge.tests.test_jobs import FakeLLM

    base, sent = server
    p = Pipeline(settings, log=lambda m: None, llm_factory=lambda pref: FallbackLLM([FakeLLM()]))
    job = p.create_from_topic("Tiny models", JobConfig(voice_mode="ask", research=False, drafts=3))
    d = call(base, f"/api/jobs/{job.id}")
    assert d["status"] == "Pick a script" and d["script"]["kind"] == "drafts" and len(d["script"]["drafts"]) == 3
    assert d["next"]["actions"][1]["args"] == ["pick", job.id, "2", "--no-interactive"]

    with pytest.raises(urllib.error.HTTPError) as e:  # cross-site posts can't add the header
        call(base, "/api/run", {"args": ["pick", job.id, "2"]}, header=False)
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:  # only pipeline commands
        call(base, "/api/run", {"args": ["voice-enroll", "x"]})
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:  # files stay inside the job folder
        call(base, f"/files/{job.id}/..%2F..%2Freelforge.db")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        call(base, "/api/create", {"source": "topic", "topic": "x"})
    assert e.value.code == 400
    assert sent == []
