"""E04: offline evaluator of the classifier against a golden set.

Everything here is SYNTHETIC: a minimal golden cut built in ``tmp_path`` and
fake LLM/embeddings. Proves the metrics, determinism across runs, the
refusal to send golden data to an external provider without the explicit
flag AND the confirmation variable, and that no database is involved.
"""

import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.eval.compare import compare_markdown
from app.eval.golden import load_cut
from app.eval.metrics import Prediction, compute_metrics
from app.eval.runner import (
    CONFIRM_ENV,
    DiskEmbeddingCache,
    EvalOptions,
    ExternalProviderRefused,
    check_external,
    default_out_dir,
    run_evaluation,
)

BACKEND = Path(__file__).resolve().parents[1]
ME = "dueno@ejemplo.gov.co"
RULES = {
    "version": "2.0.0",
    "buzon": ME,
    "ruido": {"remitentes_lista": {"valores": ["boletin@"]}},
    "identificadores": {"tarea": {"regex": "\\bT-\\d{1,3}\\b"}},
}


def _record(
    rid,
    *,
    direction="in",
    conv=None,
    subject="Asunto",
    sender="ana@otra.gov.co",
    to=(ME,),
    body="",
    dt="2026-09-01T10:00:00-05:00",
    status=None,
):
    record = {
        "id": rid,
        "conversation_id": conv,
        "folder": {"in": "inbox", "out": "sent", "event": "calendar"}[direction],
        "direction": direction,
        "subject": subject,
        "sender": sender,
        "to": list(to),
        "cc": [],
        "dt": dt,
        "body_text": body,
        "has_attachments": False,
        "attachments": [],
    }
    if direction == "event":
        record.update({"start": dt, "response_status": status, "is_cancelled": False})
    return record


def _golden(tmp_path: Path) -> Path:
    cut = tmp_path / "golden" / "2026-09-01"
    (cut / "input").mkdir(parents=True)
    records = [
        _record("m1", conv="c1", subject="Licencia T-2", body="Adjunto la licencia renovada."),
        _record("m2", conv="c2", subject="Boletín", sender="boletin@x.gov.co", to=("lista@x",)),
        _record("m3", conv="c3", subject="Nuevo pedido", body="Por favor preparar el informe X."),
        _record("m4", conv="c4", subject="Duda", body="Algo sin respuesta clara."),
        _record(
            "s1",
            direction="out",
            conv="c1",
            sender=ME,
            to=("ana@otra.gov.co",),
            body="Listo, enviado el informe final.",
            dt="2026-09-01T11:00:00-05:00",
        ),
        _record("e1", direction="event", subject="Comité", status="NotResponded"),
    ]
    (cut / "input" / "records.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    (cut / "input" / "threads.json").write_text("{}", encoding="utf-8")
    with (cut / "input" / "checklist_before.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "ID",
                "Estado",
                "Vencido",
                "Urgencia",
                "Categoría",
                "Tarea",
                "Detalle",
                "Fecha Límite",
                "Solicitante",
                "Apoyo IA",
                "Observaciones",
            ]
        )
        writer.writerow(["T-1", "PENDIENTE", "", "", "", "Informe X", "", "", "", "", ""])
        writer.writerow(["T-2", "EN CURSO", "", "", "", "Renovar licencia", "", "", "", "", ""])
    labels = [
        ("thread", "c1", "Avanza", ["T-2"]),
        ("thread", "c2", "Descartado", []),
        ("thread", "c3", "Tarea nueva", ["T-3"]),
        ("thread", "c4", None, []),
        ("sent", "s1", "Cierra", ["T-1"]),
        ("event", "e1", "No concluyente", []),
    ]
    (cut / "labels.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "record_kind": k,
                    "record_key": key,
                    "expected_result": res,
                    "expected_task_ids": tasks,
                    "confidence_of_label": "alta",
                }
            )
            + "\n"
            for k, key, res, tasks in labels
        ),
        encoding="utf-8",
    )
    (tmp_path / "reglas.json").write_text(json.dumps(RULES), encoding="utf-8")
    return tmp_path / "golden"


class ScriptedLlm(FakeLlmAdapter):
    """Answers by content: deterministic, no network."""

    async def complete(self, request):
        content = request.messages[0].content.split("Tareas candidatas")[0]
        if "licencia" in content:
            answer = {"clase": "avanza", "task_ref": "T-2", "evidencia": "la licencia renovada"}
        elif "informe final" in content:
            answer = {"clase": "cierra", "task_ref": "T-1", "evidencia": "enviado el informe final"}
        elif "preparar el informe" in content:
            answer = {"clase": "tarea_nueva", "task_ref": None, "evidencia": "preparar el informe"}
        else:
            answer = {"clase": "informativo", "task_ref": None, "evidencia": None}
        self.next_text = json.dumps({**answer, "resumen": "r"})
        return await super().complete(request)


def _options(golden: Path, tmp_path: Path, **overrides) -> EvalOptions:
    base = dict(
        golden_dir=golden,
        cuts=["2026-09-01"],
        rules_path=tmp_path / "reglas.json",
        preset="ollama_local",
        model="modelo-falso",
        embedding_model="emb-falso",
        runs=2,
        profile="server",
        out_dir=tmp_path / "out",
        cache_dir=tmp_path / "cache",
    )
    base.update(overrides)
    return EvalOptions(**base)


# --- golden loading -------------------------------------------------------------------------


def test_loads_records_tasks_and_labels_excluding_manual_needed(tmp_path):
    cut = load_cut(_golden(tmp_path), "2026-09-01")
    assert {r.kind for r in cut.records} == {"in", "out", "event"}
    assert [t.ref for t in cut.tasks] == ["T-1", "T-2"]
    assert [(lb.kind, lb.key, lb.expected) for lb in cut.labels] == [
        ("thread", "c1", "avanza"),
        ("thread", "c2", "descartado"),
        ("thread", "c3", "tarea_nueva"),
        ("sent", "s1", "cierra"),
        ("event", "e1", "no_concluyente"),
    ]
    assert cut.manual_needed == 1


# --- metrics --------------------------------------------------------------------------------


def _pred(key, expected, predicted, *, run=1, task=None, tasks=(), cands=(), out="h"):
    return Prediction(
        cut="c",
        kind="thread",
        key=key,
        run=run,
        expected=expected,
        predicted=predicted,
        task_ref=task,
        expected_tasks=tuple(tasks),
        candidate_refs=tuple(cands),
        confidence=0.5,
        stage="llm",
        reason=None,
        latency_ms=100 * run,
        input_tokens=10,
        output_tokens=5,
        error=None,
        output_hash=out,
    )


def test_metrics_accuracy_f1_confusion_and_task_scores():
    preds = [
        _pred("a", "avanza", "avanza", task="T-1", tasks=("T-1",), cands=("T-1", "T-2")),
        _pred("b", "avanza", "cierra", task="T-2", tasks=("T-1",), cands=("T-2",)),
        _pred("c", "descartado", "descartado"),
        _pred("d", "tarea_nueva", "descartado"),
    ]
    m = compute_metrics(preds, runs=1)
    assert m["n"] == 4
    assert m["class_accuracy"] == 0.5
    assert m["confusion"]["avanza"]["cierra"] == 1
    assert m["confusion"]["tarea_nueva"]["descartado"] == 1
    assert m["per_class"]["descartado"] == {
        "precision": 0.5,
        "recall": 1.0,
        "f1": 0.6667,
        "support": 1,
    }
    assert m["per_class"]["tarea_nueva"]["recall"] == 0.0
    # macro over classes present in gold or predictions: avanza 2/3, cierra 0, descartado 2/3, tn 0
    assert m["macro_f1"] == pytest.approx((0.6667 + 0 + 0.6667 + 0) / 4, abs=1e-3)
    assert m["task_top1"] == 0.5 and m["task_in_candidates"] == 0.5
    assert m["candidate_coverage"] == 0.5


def test_metrics_determinism_and_latency_percentiles():
    preds = [
        _pred("a", "avanza", "avanza", run=1, out="x"),
        _pred("a", "avanza", "avanza", run=2, out="x"),
        _pred("b", "avanza", "cierra", run=1, out="y"),
        _pred("b", "avanza", "avanza", run=2, out="z"),
    ]
    m = compute_metrics(preds, runs=2)
    assert m["determinism"]["identical_units"] == 1 and m["determinism"]["rate"] == 0.5
    assert len(m["determinism"]["run_hashes"]) == 2
    assert m["accuracy_by_run"] == [0.5, 1.0]
    assert m["latency_ms"]["p50"] == 150 and m["latency_ms"]["p95"] == 200


# --- external provider guard ----------------------------------------------------------------


def test_external_preset_is_refused_without_flag_and_confirmation():
    check_external("ollama_local", None, {})
    with pytest.raises(ExternalProviderRefused):
        check_external("openai", None, {})
    with pytest.raises(ExternalProviderRefused):
        check_external("openai", "openai", {})
    with pytest.raises(ExternalProviderRefused):
        check_external("openai", "groq", {CONFIRM_ENV: "openai"})
    check_external("openai", "openai", {CONFIRM_ENV: "openai"})


@pytest.mark.asyncio
async def test_run_refuses_external_before_reading_the_golden_set(tmp_path):
    with pytest.raises(ExternalProviderRefused):
        await run_evaluation(_options(tmp_path / "no-existe", tmp_path, preset="openai"))


# --- end to end with fakes ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_with_fakes_writes_outputs_and_is_deterministic(tmp_path):
    golden = _golden(tmp_path)
    llm = ScriptedLlm()
    metrics = await run_evaluation(
        _options(golden, tmp_path), chat_factory=lambda opts: llm, embedder_factory=lambda opts: llm
    )
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} >= {"metrics.json", "predictions.jsonl", "report.md"}
    assert metrics["n"] == 5 and metrics["manual_needed_excluded"] == 1
    assert metrics["class_accuracy"] == 1.0
    assert metrics["determinism"]["rate"] == 1.0
    assert metrics["stages"]["regla"] == 2  # noise + unattended event, no LLM
    assert metrics["config"]["determinism"]["num_gpu"] == 0
    assert metrics["config"]["rules"]["version"] == "2.0.0"
    lines = (out / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    assert "licencia" not in (out / "report.md").read_text(encoding="utf-8")
    embed_calls = len(llm.embed_calls)
    await run_evaluation(
        _options(golden, tmp_path, out_dir=tmp_path / "out2", runs=1),
        chat_factory=lambda opts: llm,
        embedder_factory=lambda opts: llm,
    )
    task_texts = {t for call in llm.embed_calls[embed_calls:] for t in call}
    assert not any(text.startswith("T-") for text in task_texts)  # task vectors from disk


@pytest.mark.asyncio
async def test_limit_takes_the_first_labeled_units(tmp_path):
    llm = ScriptedLlm()
    metrics = await run_evaluation(
        _options(_golden(tmp_path), tmp_path, runs=1, limit=2),
        chat_factory=lambda opts: llm,
        embedder_factory=lambda opts: llm,
    )
    assert metrics["n"] == 2


def test_disk_cache_round_trip(tmp_path):
    cache = DiskEmbeddingCache(tmp_path)
    cache.put("emb:0.6b", "abc", [0.5, 0.25])
    assert DiskEmbeddingCache(tmp_path).get("emb:0.6b", "abc") == [0.5, 0.25]
    assert DiskEmbeddingCache(tmp_path).get("otro", "abc") is None


def test_default_out_dir_is_outside_the_repo(tmp_path):
    out = default_out_dir(tmp_path / "golden", "qwen3.5:9b-q4_K_M", "mac", date(2026, 10, 8))
    assert out == tmp_path / "resultados" / "2026-10-08_qwen3.5-9b-q4_K_M_mac"


def test_compare_builds_a_markdown_table(tmp_path):
    for name, acc in (("a", 0.5), ("b", 0.75)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "metrics.json").write_text(
            json.dumps(
                {
                    "config": {
                        "model": f"m-{name}",
                        "profile": "mac",
                        "preset": "ollama_local",
                        "runs": 2,
                    },
                    "n": 10,
                    "class_accuracy": acc,
                    "macro_f1": 0.4,
                    "task_top1": 0.3,
                    "candidate_coverage": 0.8,
                    "per_class": {},
                    "no_concluyente_rate": 0.1,
                    "determinism": {"rate": 1.0},
                    "latency_ms": {"p50": 900, "p95": 1500},
                    "ram_bytes": 7_000_000_000,
                    "json_errors": 0,
                }
            ),
            encoding="utf-8",
        )
    table = compare_markdown([tmp_path / "a", tmp_path / "b"])
    assert table.splitlines()[0].startswith("| Modelo | Perfil")
    assert "| m-b | mac |" in table and "75,0 %" in table


def test_evaluator_imports_no_database_module():
    code = (
        "import sys; import scripts.eval_classifier, scripts.eval_compare; "
        "bad=[m for m in sys.modules if m.startswith(('app.database','asyncpg',"
        "'sqlalchemy.ext.asyncio'))]; print(bad); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- E05a: native Ollama adapter and prompt versions ---------------------------------------


def test_local_ollama_presets_use_the_native_adapter_that_honours_options(tmp_path):
    from app.ai.adapters.ollama_native import OllamaNativeAdapter
    from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
    from app.ai.presets import PRESETS
    from app.eval.runner import build_chat, uses_ollama_native

    assert uses_ollama_native(PRESETS["ollama_local"])
    assert not uses_ollama_native(PRESETS["llamacpp_local"])
    assert not any(uses_ollama_native(p) for p in PRESETS.values() if p.locality != "local")
    chat = build_chat(
        _options(tmp_path, tmp_path, base_url="http://127.0.0.1:11435/v1", profile="server")
    )
    assert isinstance(chat, OllamaNativeAdapter)
    body = chat._body(
        __import__("app.ai.ports", fromlist=["LlmRequest"]).LlmRequest(
            system="s", messages=(), max_tokens=10
        )
    )
    assert body["options"]["num_ctx"] == 8192 and body["options"]["num_gpu"] == 0
    assert chat._base_url == "http://127.0.0.1:11435"
    assert isinstance(
        build_chat(_options(tmp_path, tmp_path, preset="llamacpp_local")), (OpenAiCompatibleAdapter)
    )


@pytest.mark.asyncio
async def test_prompt_version_is_recorded_in_predictions_and_config(tmp_path):
    from app.modules.reconciliation.prompt_versions import PROMPTS_V2

    version = sorted(PROMPTS_V2)[0]
    llm = ScriptedLlm()
    metrics = await run_evaluation(
        _options(_golden(tmp_path), tmp_path, runs=1, prompt_version=version),
        chat_factory=lambda opts: llm,
        embedder_factory=lambda opts: llm,
    )
    assert metrics["config"]["prompt_version"] == version
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "predictions.jsonl").read_text("utf-8").splitlines()
    ]
    assert {row["prompt_version"] for row in rows} == {version}
    assert {c.prompt_version for c in llm.calls} == {version}


def test_cli_refuses_an_unknown_prompt_version(capsys):
    from scripts.eval_classifier import main

    with pytest.raises(SystemExit):
        main(["--golden-dir", "x", "--cortes", "c", "--rules", "r", "--prompt-version", "nope"])


@pytest.mark.asyncio
async def test_subject_match_option_reaches_the_channel_config(tmp_path):
    llm = ScriptedLlm()
    metrics = await run_evaluation(
        _options(_golden(tmp_path), tmp_path, runs=1, subject_match=True),
        chat_factory=lambda opts: llm,
        embedder_factory=lambda opts: llm,
    )
    assert metrics["config"]["subject_match"] is True


# --- E07b: candidate coverage only (no chat model) -------------------------------------------


@pytest.mark.asyncio
async def test_candidates_only_never_builds_the_chat_model_and_measures_coverage(tmp_path):
    embedder = ScriptedLlm()

    def no_chat(opts):
        raise AssertionError("candidates-only must not build the chat model")

    metrics = await run_evaluation(
        _options(_golden(tmp_path), tmp_path, runs=3, candidates_only=True),
        chat_factory=no_chat,
        embedder_factory=lambda opts: embedder,
    )
    assert embedder.calls == []
    assert metrics["runs"] == 1 and metrics["config"]["candidates_only"] is True
    assert metrics["candidate_coverage"] is not None
    assert metrics["stages"].get("llm", 0) == 0
    lines = (tmp_path / "out" / "predictions.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert rows and all(r["predicted"] is None for r in rows if r["stage"] == "sin_llm")


@pytest.mark.asyncio
async def test_retrieval_options_reach_the_channel_config(tmp_path):
    metrics = await run_evaluation(
        _options(
            _golden(tmp_path),
            tmp_path,
            candidates_only=True,
            task_text="full",
            ranking="rrf",
            object_match="off",
            top_k=8,
        ),
        embedder_factory=lambda opts: ScriptedLlm(),
    )
    config = metrics["config"]
    assert (config["task_text"], config["ranking"], config["object_match"], config["top_k"]) == (
        "full",
        "rrf",
        "off",
        8,
    )


def test_cli_accepts_the_retrieval_flags(tmp_path, monkeypatch):
    from scripts import eval_classifier

    seen = {}

    async def fake_run(options):
        seen["options"] = options
        return {
            "n": 0,
            "class_accuracy": None,
            "macro_f1": None,
            "task_top1": None,
            "candidate_coverage": 0.5,
            "determinism": {"rate": None},
            "latency_ms": {"p50": None, "p95": None},
            "json_errors": 0,
            "out_dir": str(tmp_path),
        }

    monkeypatch.setattr(eval_classifier, "run_evaluation", fake_run)
    code = eval_classifier.main(
        [
            "--golden-dir", str(tmp_path), "--rules", str(tmp_path / "r.json"),
            "--cortes", "2026-09-01", "--candidates-only", "--task-text", "full",
            "--ranking", "bm25", "--object-match", "specific", "--top-k", "10",
        ]
    )  # fmt: skip
    options = seen["options"]
    assert code == 0
    assert options.candidates_only and options.task_text == "full"
    assert options.ranking == "bm25" and options.object_match == "specific" and options.top_k == 10


def test_cli_num_batch_reaches_the_determinism_options(tmp_path, monkeypatch):
    from app.eval.runner import determinism_for
    from scripts import eval_classifier

    seen = {}

    async def fake_run(options):
        seen["options"] = options
        return {
            "n": 0,
            "class_accuracy": None,
            "macro_f1": None,
            "task_top1": None,
            "candidate_coverage": None,
            "determinism": {"rate": None},
            "latency_ms": {"p50": None, "p95": None},
            "json_errors": 0,
            "out_dir": str(tmp_path),
        }

    monkeypatch.setattr(eval_classifier, "run_evaluation", fake_run)
    code = eval_classifier.main(
        [
            "--golden-dir", str(tmp_path), "--rules", str(tmp_path / "r.json"),
            "--cortes", "2026-09-01", "--profile", "server", "--num-thread", "1",
            "--num-batch", "256",
        ]
    )  # fmt: skip
    assert code == 0
    options = seen["options"]
    assert options.num_batch == 256
    determinism = determinism_for(options)
    assert determinism.num_batch == 256 and determinism.num_thread == 1
