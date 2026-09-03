"""Create an offline, read-only, educational HTML analysis of the N6 ML pipeline."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import warnings
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlparse

import numpy as np

from common import (CONFIG_ROOT, MODELS_ROOT, PREPARED_ROOT, RAW_ROOT,
                    REPORTS_ROOT, REVIEW_PATH, STATE_ROOT, TRAINING_ROOT,
                    class_names, load_json, reviewed_rows, sha256_file,
                    utc_now)
from dataset import load_depth_record, preprocess_depth


PAGES = (
    ("index.html", "סקירה"),
    ("dataset.html", "הנתונים"),
    ("training.html", "האימון"),
    ("predictions.html", "הפריימים"),
    ("quantization.html", "Quantization"),
    ("npu_hil.html", "NPU / HIL"),
    ("files.html", "מקורות"),
)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = load_json(path)
    return value if isinstance(value, dict) else {}


def fmt_percent(value: Any, digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "לא זמין"
    if not math.isfinite(number):
        return "לא זמין"
    return f"{number * 100:.{digits}f}%"


def fmt_number(value: Any, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "לא זמין"
    if not math.isfinite(number):
        return "לא זמין"
    return f"{number:.{digits}f}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def relative_url(path: Path, report_dir: Path) -> str:
    try:
        relative = os.path.relpath(path.resolve(), report_dir.resolve())
        return quote(Path(relative).as_posix(), safe="/._-")
    except (OSError, ValueError):
        return path.resolve().as_uri()


def discover_metadata() -> tuple[list[dict[str, Any]], list[Path]]:
    files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    records = reviewed_rows(files)
    return records, files


def prepared_split_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        path = PREPARED_ROOT / f"{split}.npz"
        if not path.exists():
            continue
        with np.load(path, allow_pickle=False) as archive:
            for digest in archive.get("hashes", np.asarray([], dtype="U64")):
                result[str(digest)] = split
    return result


def read_history() -> list[dict[str, float]]:
    path = REPORTS_ROOT / "training_history.csv"
    if not path.exists():
        return []
    rows: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            converted: dict[str, float] = {}
            for key, value in row.items():
                try:
                    converted[key] = float(value)
                except (TypeError, ValueError):
                    continue
            rows.append(converted)
    return rows


def classification_metrics(labels: Iterable[int], predictions: Iterable[int],
                           count: int) -> dict[str, Any]:
    expected = np.asarray(list(labels), dtype=np.int64)
    predicted = np.asarray(list(predictions), dtype=np.int64)
    matrix = np.zeros((count, count), dtype=np.int64)
    for truth, guess in zip(expected, predicted):
        if 0 <= truth < count and 0 <= guess < count:
            matrix[truth, guess] += 1
    per_class = []
    for index in range(count):
        true_positive = int(matrix[index, index])
        support = int(matrix[index].sum())
        predicted_count = int(matrix[:, index].sum())
        recall = true_positive / support if support else 0.0
        precision = true_positive / predicted_count if predicted_count else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall else 0.0)
        per_class.append({
            "index": index,
            "support": support,
            "correct": true_positive,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })
    accuracy = float(np.mean(expected == predicted)) if len(expected) else None
    return {
        "samples": int(len(expected)),
        "accuracy": accuracy,
        "matrix": matrix.tolist(),
        "per_class": per_class,
        "macro_recall": (float(np.mean([item["recall"] for item in per_class]))
                         if per_class else None),
        "macro_f1": (float(np.mean([item["f1"] for item in per_class]))
                     if per_class else None),
    }


def summarize_scores(scores: np.ndarray) -> tuple[int, float, float, bool]:
    """Return firmware-compatible class, confidence, top-two margin and tie."""
    values = np.asarray(scores)
    prediction_id = int(np.argmax(values))
    ordered = np.sort(values.astype(np.float64))[::-1]
    confidence = float(values[prediction_id])
    margin = float(ordered[0] - ordered[1]) if len(ordered) > 1 else confidence
    tied = bool(np.count_nonzero(values == values[prediction_id]) > 1)
    return prediction_id, confidence, margin, tied


def enrich_and_infer(records: list[dict[str, Any]], split_map: dict[str, str],
                     skip_inference: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    names = class_names()
    name_to_id = {name: index for index, name in enumerate(names)}
    pre_cfg = read_json(CONFIG_ROOT / "preprocessing.json")
    tensors: list[np.ndarray] = []
    enriched: list[dict[str, Any]] = []
    errors: list[str] = []
    for source in records:
        row = dict(source)
        row["split"] = split_map.get(str(row.get("depth_sha256", "")), "unassigned")
        row["label_id"] = name_to_id.get(str(row.get("label")), -1)
        try:
            tensor = preprocess_depth(load_depth_record(row), pre_cfg)
            image = tensor[..., 0]
            nonzero = np.argwhere(image > 0)
            row["model_nonzero_ratio"] = float(np.mean(image > 0))
            if len(nonzero):
                row["model_centroid_x"] = float(np.mean(nonzero[:, 1]) /
                                                max(1, image.shape[1] - 1))
                row["model_centroid_y"] = float(np.mean(nonzero[:, 0]) /
                                                max(1, image.shape[0] - 1))
            else:
                row["model_centroid_x"] = None
                row["model_centroid_y"] = None
            tensors.append(tensor)
            row["tensor_index"] = len(tensors) - 1
        except Exception as exc:
            row["tensor_index"] = None
            row["analysis_error"] = f"{type(exc).__name__}: {exc}"
            errors.append(f"{row.get('npz', '?')}: {row['analysis_error']}")
        enriched.append(row)

    status: dict[str, Any] = {
        "requested": not skip_inference,
        "tensorflow_loaded": False,
        "float_model": False,
        "tflite_model": False,
        "errors": errors,
    }
    if skip_inference or not tensors:
        return enriched, status

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    try:
        import tensorflow as tf
        status["tensorflow_loaded"] = True
    except Exception as exc:
        status["errors"].append(
            f"TensorFlow could not be loaded: {type(exc).__name__}: {exc}")
        return enriched, status

    batch = np.stack(tensors).astype(np.uint8)
    float_path = MODELS_ROOT / "rps_float.keras"
    if float_path.exists():
        try:
            model = tf.keras.models.load_model(float_path)
            outputs = np.asarray(model.predict(batch, verbose=0), dtype=np.float32)
            for row in enriched:
                index = row.get("tensor_index")
                if index is None:
                    continue
                probabilities = outputs[index]
                prediction_id, confidence, margin, tied = summarize_scores(
                    probabilities
                )
                row["float_prediction_id"] = prediction_id
                row["float_prediction"] = names[prediction_id]
                row["float_confidence"] = confidence
                row["float_margin"] = margin
                row["float_tie"] = tied
                row["float_scores"] = [float(value) for value in probabilities]
            status["float_model"] = True
        except Exception as exc:
            status["errors"].append(
                f"Keras inference failed: {type(exc).__name__}: {exc}")

    tflite_path = MODELS_ROOT / "rps_int8.tflite"
    if tflite_path.exists():
        try:
            warnings.filterwarnings(
                "ignore",
                message=r".*tf\.lite\.Interpreter is deprecated.*",
                category=UserWarning,
            )
            interpreter = tf.lite.Interpreter(model_path=str(tflite_path))
            interpreter.allocate_tensors()
            input_info = interpreter.get_input_details()[0]
            output_info = interpreter.get_output_details()[0]
            output_scale, output_zero = output_info["quantization"]
            for row in enriched:
                index = row.get("tensor_index")
                if index is None:
                    continue
                sample = batch[index:index + 1].astype(input_info["dtype"])
                interpreter.set_tensor(input_info["index"], sample)
                interpreter.invoke()
                raw = interpreter.get_tensor(output_info["index"])[0]
                dequantized = ((raw.astype(np.float32) - float(output_zero)) *
                               float(output_scale))
                # np.argmax returns the first class on a tie. The firmware uses
                # the same strict `>` scan, so this detail is part of the
                # deployed class-selection contract.
                prediction_id, confidence, margin, tied = summarize_scores(
                    dequantized
                )
                row["tflite_prediction_id"] = prediction_id
                row["tflite_prediction"] = names[prediction_id]
                row["tflite_confidence"] = confidence
                row["tflite_margin"] = margin
                row["tflite_tie"] = tied
                row["tflite_raw_scores"] = [int(value) for value in raw]
                row["tflite_scores"] = [float(value) for value in dequantized]
                row["tflite_correct"] = (row["tflite_prediction_id"] ==
                                         row.get("label_id"))
                if "float_prediction_id" in row:
                    row["float_tflite_agree"] = (
                        row["float_prediction_id"] == row["tflite_prediction_id"]
                    )
            status["tflite_model"] = True
            status["tflite_input"] = {
                "shape": input_info["shape"].astype(int).tolist(),
                "dtype": str(input_info["dtype"]),
            }
            status["tflite_output"] = {
                "shape": output_info["shape"].astype(int).tolist(),
                "dtype": str(output_info["dtype"]),
                "scale": float(output_scale),
                "zero_point": int(output_zero),
            }
        except Exception as exc:
            status["errors"].append(
                f"TFLite inference failed: {type(exc).__name__}: {exc}")
    return enriched, status


def source_info(path: Path, description: str, report_dir: Path,
                hash_file: bool = True) -> dict[str, Any]:
    result = {
        "path": str(path.resolve()),
        "display_path": str(path.resolve().relative_to(TRAINING_ROOT.resolve()))
        if TRAINING_ROOT.resolve() in path.resolve().parents else str(path.resolve()),
        "description": description,
        "exists": path.exists(),
        "url": relative_url(path, report_dir),
    }
    if path.exists():
        stat = path.stat()
        result.update({
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "sha256": sha256_file(path) if hash_file and path.is_file() else None,
        })
    return result


def badge(kind: str, title: str, text: str) -> str:
    return (f'<article class="status-card {esc(kind)}"><div class="status-dot"></div>'
            f'<div><h3>{esc(title)}</h3><p>{esc(text)}</p></div></article>')


def metric_card(title: str, value: str, note: str = "") -> str:
    return (f'<article class="metric"><span>{esc(title)}</span><strong>{esc(value)}</strong>'
            f'<small>{esc(note)}</small></article>')


def notice(kind: str, title: str, body: str) -> str:
    return (f'<aside class="notice {esc(kind)}"><strong>{esc(title)}</strong>'
            f'<p>{esc(body)}</p></aside>')


def table(headers: list[str], rows: list[list[Any]], classes: str = "") -> str:
    head = "".join(f"<th>{esc(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{item if isinstance(item, Html) else esc(item)}</td>"
                           for item in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table class="{esc(classes)}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class Html(str):
    """Marker for intentionally generated HTML cells."""


def nav(active: str) -> str:
    links = []
    for filename, label in PAGES:
        current = " active" if filename == active else ""
        links.append(f'<a class="{current.strip()}" href="{filename}">{esc(label)}</a>')
    return "".join(links)


def page(active: str, title: str, subtitle: str, body: str,
         report_id: str, scripts: str = "") -> str:
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{esc(title)} — N6 Training Analysis</title>
  <link rel="stylesheet" href="report.css">
</head>
<body>
  <header class="topbar">
    <div><span class="eyebrow">N6 TRAINING ANALYSIS</span><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>
    <div class="run-id"><span>Analysis snapshot</span><code>{esc(report_id)}</code></div>
  </header>
  <nav>{nav(active)}</nav>
  <main>{body}</main>
  <footer><p>הדוח נוצר מקומית. הוא אינו מאמן מודל, משנה raw data או ניגש ללוח.</p></footer>
  <script src="report.js"></script>
  {scripts}
</body>
</html>
"""


def confusion_html(matrix: list[list[int]], names: list[str]) -> str:
    maximum = max((max(row) for row in matrix if row), default=1)
    header = "<th>אמת ↓ / חיזוי →</th>" + "".join(f"<th>{esc(name)}</th>" for name in names)
    rows = []
    for index, values in enumerate(matrix):
        total = sum(values)
        cells = []
        for column, value in enumerate(values):
            ratio = value / total if total else 0.0
            intensity = 0.12 + 0.58 * (value / maximum if maximum else 0.0)
            color = "34,197,94" if index == column else "239,68,68"
            cells.append(
                f'<td style="background:rgba({color},{intensity:.3f})">'
                f'<strong>{value}</strong><small>{fmt_percent(ratio, 0)}</small></td>'
            )
        rows.append(f"<tr><th>{esc(names[index])}</th>{''.join(cells)}</tr>")
    return (f'<div class="table-wrap"><table class="confusion"><thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def build_dataset_page(context: dict[str, Any], report_id: str) -> str:
    records = context["records"]
    names = context["classes"]
    validation = context["validation"]
    manifest = context["prepared_manifest"]
    by_label = Counter(str(row.get("label", "unknown")) for row in records)
    sessions = {str(row.get("session_id", "unknown")) for row in records}
    bursts_by_label: defaultdict[str, set[str]] = defaultdict(set)
    for row in records:
        bursts_by_label[str(row.get("label"))].add(str(row.get("burst_id", "missing")))
    rows = []
    for name in names:
        split_counts = [sum(1 for row in records if row.get("label") == name and row.get("split") == split)
                        for split in ("train", "validation", "test")]
        rows.append([name, by_label[name], len(bursts_by_label[name]), *split_counts])
    cards = "".join((
        metric_card("פריימים", str(len(records)), "רשומות accepted"),
        metric_card("Sessions", str(len(sessions)), "ימי/סבבי צילום עצמאיים"),
        metric_card("Bursts", str(sum(len(value) for value in bursts_by_label.values())), "קבוצות צילום רציפות"),
        metric_card("כפילויות זהות", str(validation.get("exact_duplicate_frames", "לא זמין")), "לא כולל near-duplicates"),
        metric_card("Reviewed", str(validation.get("reviewed_records", 0)), "החלטות אנושיות"),
        metric_card("Rejected", str(validation.get("rejected_records", 0)), "RAW נשמר בצד"),
        metric_card("Relabeled", str(validation.get("relabeled_records", 0)), "label מתוקן"),
    ))
    warnings = validation.get("warnings", [])
    warning_html = "".join(notice("warn", "אזהרת dataset", str(item)) for item in warnings)
    split_strategy = manifest.get("split_strategy", "אין manifest מוכן")
    body = f"""
<section class="hero-grid">{cards}</section>
{notice("info", "מה הדף הזה בודק?", "כמות קבצים לבדה אינה מספיקה. Sessions ו-bursts מלמדים כמה מצבים עצמאיים באמת נמדדו, וה-split מראה מה שימש ללמידה ומה נשמר לבדיקה.")}
{warning_html}
<section><h2>התפלגות המחלקות וה־splits</h2>
{table(["מחלקה", "סה״כ", "Bursts", "Train", "Validation", "Test"], rows)}
<p class="explain"><strong>איך לקרוא:</strong> פריימים מאותו burst נשארים יחד באותו split. כך פריימים סמוכים וכמעט זהים אינם מופיעים גם באימון וגם ב-test.</p></section>
<section><h2>אסטרטגיית החלוקה</h2><code class="block">{esc(split_strategy)}</code>
<p class="explain">Test אמין צריך להכיל sessions או לפחות bursts שלא שימשו לבחירת המשקולות. כאשר כל הנתונים מגיעים מ-session יחיד, המדידה עדיין מוגבלת לאותו אדם, רקע ותנאי צילום.</p></section>
<section><h2>מה נבדק ומה עדיין לא</h2>
<div class="two-column">
<article class="panel"><h3>נבדק</h3><ul><li>קבצי NPZ ו-PNG קיימים</li><li>shape ו-dtype</li><li>SHA-256 של העומק</li><li>איזון בין מחלקות</li><li>כפילויות זהות</li><li>invalid ratio</li></ul></article>
<article class="panel"><h3>עדיין לא מדד עצמאי</h3><ul><li>near-duplicates חזותיים</li><li>גיוון בין אנשים</li><li>גיוון בין חדרים ורקעים</li><li>ביצועים על session חיצוני לחלוטין</li><li>דיוק labels אנושי</li></ul></article>
</div></section>
"""
    return page("dataset.html", "איכות הנתונים", "מה באמת צולם וכיצד חולק", body, report_id)


def build_training_page(context: dict[str, Any], report_id: str) -> str:
    names = context["classes"]
    report = context["float_report"]
    history = context["history"]
    matrix = report.get("confusion_matrix_rows_expected_columns_predicted", [])
    if not matrix:
        matrix = [[0 for _ in names] for _ in names]
    # This page explains the Keras float report, so derive every displayed
    # per-class metric from its matrix. TFLite metrics belong on the separate
    # quantization page and must not silently mix with float measurements.
    metrics = classification_metrics(
        [index for index, row in enumerate(matrix) for _ in range(sum(row))],
        [column for row in matrix for column, value in enumerate(row)
         for _ in range(value)],
        len(names),
    )
    metric_rows = []
    for index, name in enumerate(names):
        item = metrics["per_class"][index]
        metric_rows.append([name, item["support"], item["correct"],
                            fmt_percent(item["precision"]), fmt_percent(item["recall"]),
                            fmt_percent(item["f1"])])
    train_best = max((row.get("accuracy", 0.0) for row in history), default=0.0)
    validation_best = max((row.get("val_accuracy", 0.0) for row in history), default=0.0)
    gap = train_best - validation_best
    overfit_text = ("קיים פער גדול בין training ל-validation — סימן אפשרי ל-overfitting."
                    if gap >= 0.15 else
                    "לא זוהה פער חריג לפי כלל האצבע של 15 נקודות אחוז.")
    charts = {
        "accuracy": {
            "labels": [int(row.get("epoch", index + 1)) for index, row in enumerate(history)],
            "series": [
                {"name": "Training accuracy", "color": "#38bdf8", "values": [row.get("accuracy") for row in history]},
                {"name": "Validation accuracy", "color": "#f59e0b", "values": [row.get("val_accuracy") for row in history]},
            ], "percent": True,
        },
        "loss": {
            "labels": [int(row.get("epoch", index + 1)) for index, row in enumerate(history)],
            "series": [
                {"name": "Training loss", "color": "#22c55e", "values": [row.get("loss") for row in history]},
                {"name": "Validation loss", "color": "#ef4444", "values": [row.get("val_loss") for row in history]},
            ], "percent": False,
        },
    }
    body = f"""
<section class="hero-grid">
{metric_card("Test accuracy", fmt_percent(report.get("test_accuracy")), "כל הפריימים ב-test")}
{metric_card("Macro accuracy", fmt_percent(report.get("test_macro_accuracy")), "משקל שווה לכל מחלקה")}
{metric_card("Parameters", f'{int(report.get("model_parameters", 0)):,}', "משקולות ופרמטרים")}
{metric_card("Train / validation gap", fmt_percent(gap), "best training פחות best validation")}
</section>
{notice("warn" if gap >= 0.15 else "info", "פירוש עקומות הלמידה", overfit_text)}
<section><h2>Accuracy לפי epoch</h2><canvas class="chart" data-chart="accuracy"></canvas>
<p class="explain">Training accuracy מודד את הדוגמאות שהמודל ראה בזמן הלמידה. Validation accuracy מודד דוגמאות שלא שימשו לעדכון המשקולות. שיפור ב-training לצד עצירה או ירידה ב-validation מעיד שהמודל מתחיל לשנן.</p></section>
<section><h2>Loss לפי epoch</h2><canvas class="chart" data-chart="loss"></canvas>
<p class="explain">Loss מודד את גודל הטעות, לא רק אם המחלקה הסופית נכונה. Validation loss שעולה בזמן training loss יורד הוא סימן חשוב ל-overfitting.</p></section>
<section><h2>Confusion matrix</h2>
{notice("info", "איך קוראים את הטבלה?", "השורות הן ה-label האמיתי והעמודות הן תשובת המודל. האלכסון הירוק הוא תשובות נכונות; תאים אדומים מראים בין אילו מחלקות המודל התבלבל.")}
{confusion_html(matrix, names)}</section>
<section><h2>מדדים לכל מחלקה</h2>
{table(["מחלקה", "דוגמאות", "נכונות", "Precision", "Recall / accuracy", "F1"], metric_rows)}
<div class="glossary"><p><strong>Precision:</strong> כאשר המודל אמר מחלקה מסוימת, באיזו תדירות הוא צדק.</p><p><strong>Recall:</strong> מתוך כל הדוגמאות האמיתיות של המחלקה, כמה הוא מצא.</p><p><strong>F1:</strong> איזון בין Precision ל-Recall.</p></div></section>
"""
    scripts = f'<script>window.reportCharts={json_script(charts)}; renderAllCharts();</script>'
    return page("training.html", "תוצאות האימון", "עקומות למידה, טעויות ומדדים לכל מחלקה", body, report_id, scripts)


def score_table(row: dict[str, Any], names: list[str]) -> str:
    raw = row.get("tflite_raw_scores")
    if not raw:
        return '<span class="muted">אין inference</span>'
    return " ".join(f'<span class="score"><b>{esc(name)}</b> {int(value)}</span>'
                    for name, value in zip(names, raw))


def build_predictions_page(context: dict[str, Any], report_id: str,
                           report_dir: Path) -> str:
    names = context["classes"]
    records = context["records"]
    cards = []
    for index, row in enumerate(records):
        preview_path = TRAINING_ROOT / str(row.get("preview_png", ""))
        model_path = TRAINING_ROOT / str(row.get("model_input_png", ""))
        preview_url = relative_url(preview_path, report_dir) if preview_path.exists() else ""
        model_url = relative_url(model_path, report_dir) if model_path.exists() else ""
        label = str(row.get("label", "unknown"))
        prediction = str(row.get("tflite_prediction", "unavailable"))
        correct = row.get("tflite_correct")
        correct_text = "נכון" if correct is True else "שגוי" if correct is False else "לא נבדק"
        correct_class = "correct" if correct is True else "wrong" if correct is False else "unknown"
        confidence = row.get("tflite_confidence")
        confidence_value = float(confidence) if confidence is not None else -1.0
        agreement = row.get("float_tflite_agree")
        agreement_value = "yes" if agreement is True else "no" if agreement is False else "unknown"
        images = []
        if preview_url:
            images.append(f'<figure><img loading="lazy" src="{preview_url}" alt="Raw depth preview"><figcaption>Raw depth preview</figcaption></figure>')
        if model_url:
            images.append(f'<figure><img loading="lazy" src="{model_url}" alt="Model input"><figcaption>Model input 64×50</figcaption></figure>')
        cards.append(f"""
<article class="prediction-card {correct_class}" data-label="{esc(label)}" data-prediction="{esc(prediction)}"
 data-split="{esc(row.get('split', 'unassigned'))}" data-result="{correct_class}"
 data-agreement="{agreement_value}" data-confidence="{confidence_value:.6f}">
 <div class="prediction-images">{''.join(images)}</div>
 <div class="prediction-info">
  <span class="result-pill">{correct_text}</span><small>#{index + 1} · {esc(row.get('split', 'unassigned'))}</small>
  <h3>{esc(label)} <span>← אמת</span></h3>
  <p class="prediction-answer"><strong>{esc(prediction)}</strong> ← TFLite</p>
  <p>Confidence: <b>{fmt_percent(confidence)}</b> · Margin: <b>{fmt_percent(row.get('tflite_margin'))}</b>{' · <b>שוויון בין ציונים</b>' if row.get('tflite_tie') else ''}</p>
  <div class="scores" dir="ltr">{score_table(row, names)}</div>
  <details><summary>פרטי מקור</summary><code>{esc(row.get('npz', ''))}</code><p>Session: {esc(row.get('session_id', ''))}<br>Burst: {esc(row.get('burst_id', ''))}</p></details>
 </div>
</article>""")
    option_names = "".join(f'<option value="{esc(name)}">{esc(name)}</option>' for name in names)
    body = f"""
{notice("info", "זו סימולציה של המודל שנכנס ל-FW", "כל raw frame עובר שוב את ה-preprocessing הנוכחי ומוזן ל-rps_int8.tflite. זה מדמה את החלטת המודל; חומרת Neural-ART עצמה נבדקת רק ב-HIL.")}
{notice("warn", "חשוב", "תשובה נכונה על פריים מתוך train אינה מדד אובייקטיבי. השתמש במסנן Split והתמקד ב-test וב-sessions שלא השתתפו באימון.")}
<section class="filters">
 <label>Label<select id="filter-label"><option value="all">הכול</option>{option_names}</select></label>
 <label>Prediction<select id="filter-prediction"><option value="all">הכול</option>{option_names}<option value="unavailable">לא זמין</option></select></label>
 <label>Split<select id="filter-split"><option value="all">הכול</option><option value="train">train</option><option value="validation">validation</option><option value="test">test</option><option value="unassigned">unassigned</option></select></label>
 <label>תוצאה<select id="filter-result"><option value="all">הכול</option><option value="wrong">טעויות בלבד</option><option value="correct">נכונות בלבד</option><option value="unknown">לא נבדק</option></select></label>
 <label>התאמת Float/INT8<select id="filter-agreement"><option value="all">הכול</option><option value="yes">מסכימים</option><option value="no">חלוקים</option><option value="unknown">לא זמין</option></select></label>
 <label>Confidence עד<input id="filter-confidence" type="range" min="0" max="100" value="100"><output id="confidence-output">100%</output></label>
</section>
<p id="visible-count" class="visible-count"></p>
<section id="prediction-gallery" class="prediction-grid">{''.join(cards) if cards else '<p>לא נמצאו פריימים.</p>'}</section>
"""
    scripts = "<script>setupPredictionFilters();</script>"
    return page("predictions.html", "גלריית פריימים ותחזיות", "לראות בדיוק מה נכנס למודל ומה הוא ענה", body, report_id, scripts)


def build_quantization_page(context: dict[str, Any], report_id: str) -> str:
    report = context["quant_report"]
    inference = context["inference"]
    test_rows = [row for row in context["records"] if row.get("split") == "test" and
                 "float_tflite_agree" in row]
    disagreements = sum(row.get("float_tflite_agree") is False for row in test_rows)
    input_info = report.get("input", {})
    output_info = report.get("output", {})
    body = f"""
<section class="hero-grid">
{metric_card("Float macro accuracy", fmt_percent(report.get("float_test_macro_accuracy")), "לפני quantization")}
{metric_card("INT8 macro accuracy", fmt_percent(report.get("test_macro_accuracy")), "אחרי quantization")}
{metric_card("Accuracy drop", fmt_percent(report.get("quantization_accuracy_drop")), "נמוך יותר עדיף")}
{metric_card("Model size", f'{int(report.get("model_size_bytes", 0)):,} bytes', "rps_int8.tflite")}
</section>
{notice("info", "מהו Quantization?", "המרה של החישובים והמשקולות מ-float למספרים שלמים קטנים. ה-NPU מקבל מודל INT8/UINT8 יעיל יותר, אבל חייבים למדוד האם ההמרה שינתה את התוצאות.")}
<section><h2>חוזה הקלט והפלט</h2>
{table(["Tensor", "Shape", "dtype", "Scale", "Zero point"], [
    ["Input", input_info.get("shape", ""), input_info.get("dtype", ""), input_info.get("scale", ""), input_info.get("zero_point", "")],
    ["Output", output_info.get("shape", ""), output_info.get("dtype", ""), output_info.get("scale", ""), output_info.get("zero_point", "")],
])}
<p class="explain">זהו ה-ABI בין Python, קובץ TFLite, הקוד ש-STEdgeAI יוצר וה-firmware. שינוי shape, dtype, סדר מחלקות או preprocessing מחייב בנייה ושילוב מחדש.</p></section>
<section><h2>Float מול INT8 על הפריימים השמורים</h2>
{metric_card("Test disagreements", str(disagreements), f"מתוך {len(test_rows)} פריימי test שנבדקו")}
<p class="explain">אי-הסכמה פירושה שמודל Keras ומודל TFLite בחרו class שונה. גם כאשר ה-class זהה, אפשר לבדוק ב-HIL את ההפרש בין ציוני ה-int8 הגולמיים.</p></section>
<section><h2>Representative dataset</h2><p>בזמן ההמרה נבחרות עד 200 דוגמאות אמיתיות מתוך train. TensorFlow משתמש בהן כדי לבחור scale ו-zero-point לטווחי הביניים. הן אינן מלמדות את המודל מחדש; הן מכיילות את ההמרה המספרית.</p></section>
{''.join(notice("warn", "שגיאת inference", item) for item in inference.get("errors", []))}
"""
    return page("quantization.html", "Quantization", "Keras float מול TFLite INT8", body, report_id)


def build_hil_page(context: dict[str, Any], report_id: str) -> str:
    hil = context["hil_report"]
    comparison = hil.get("npu_comparison", {})
    requirements = comparison.get("requirements", {})
    result = str(hil.get("result", "not available"))
    kind = "good" if result == "pass" else "bad" if result == "fail" else "warn"
    body = f"""
{notice(kind, f"תוצאת דוח HIL: {result}", "העמוד מציג את קובץ hil_validation.json הנוכחי. הרצה חדשה של 09_HIL.bat עשויה להחליף אותו; מערכת runs מלאה תתווסף בשלב נפרד.")}
<section class="hero-grid">
{metric_card("Frames", str(hil.get("frames", "לא זמין")), "CRC-valid frames")}
{metric_card("NPU coverage", fmt_percent(comparison.get("coverage")), f'נדרש {fmt_percent(requirements.get("coverage"))}')}
{metric_card("Class agreement", fmt_percent(comparison.get("class_agreement")), f'נדרש {fmt_percent(requirements.get("class_agreement"))}')}
{metric_card("Max raw-score delta", str(comparison.get("maximum_raw_score_delta", "לא זמין")), f'מקסימום מותר {requirements.get("maximum_raw_score_delta", "לא זמין")}')}
{metric_card("Observed FPS", fmt_number(hil.get("observed_fps")), f'נדרש {hil.get("required_capture_fps", "לא זמין")}')}
{metric_card("CRC errors", str(hil.get("parser_crc_errors", "לא זמין")), "צריך להיות 0")}
</section>
{notice("info", "מה HIL כן מוכיח", "אותו frame עבר preprocessing ו-TFLite במחשב, ובמקביל Neural-ART בלוח. Coverage, run counter, class agreement ו-raw scores בודקים שה-deployment נאמן למודל.")}
{notice("warn", "מה HIL לא מוכיח", "אם המחשב וה-NPU נותנים יחד אותה תשובה שגויה, HIL עדיין יכול לעבור. איכות הזיהוי נמדדת מול labels ב-test וב-session חיצוני.")}
<section><h2>בדיקות תחבורה וחיות</h2>
{table(["בדיקה", "ערך", "פירוש"], [
    ["Unique payloads", hil.get("unique_payload_crc32", ""), "מוכיח שלא שודר אותו frame שוב ושוב"],
    ["Missing frame ratio", fmt_percent(hil.get("missing_frame_ratio")), "דילוגים ב-CDC; לא כשל לבדו אם הקצב מספיק"],
    ["Run counter monotonic", comparison.get("run_counter_monotonic", ""), "מונה עולה מוכיח שה-NPU ממשיך לרוץ"],
    ["Framing candidates rejected", hil.get("parser_framing_candidates_rejected", ""), "resynchronization של ה-parser"],
    ["Discarded bytes", hil.get("parser_discarded_bytes", ""), "טקסט/bytes שנדחו בדרך לרשומה תקינה"],
])}</section>
"""
    return page("npu_hil.html", "NPU ו־Hardware-in-the-loop", "האם הלוח מריץ נאמנה את אותו מודל", body, report_id)


def build_files_page(context: dict[str, Any], report_id: str) -> str:
    rows = []
    for source in context["sources"]:
        link = Html(f'<a href="{source["url"]}"><code>{esc(source["display_path"])}</code></a>')
        digest = source.get("sha256")
        rows.append([
            link,
            source["description"],
            "קיים" if source["exists"] else "חסר",
            source.get("modified", ""),
            Html(f'<code title="{esc(digest or "")}">{esc((digest or "")[:12])}</code>'),
        ])
    body = f"""
{notice("info", "אין כאן מספרים מומצאים", "כל מסקנה בדוח מגיעה מאחד הקבצים למטה או מ-inference מקומי על ה-raw frames בעזרת המודל השמור. ה-hash עוזר לזהות אם המקור השתנה בין snapshots.")}
<section><h2>קובצי המקור</h2>{table(["קובץ", "תפקיד", "מצב", "עודכן", "SHA-256"], rows)}</section>
<section><h2>Log לעומת Report</h2>
<div class="two-column"><article class="panel"><h3>Log</h3><p>רצף אירועים טכני: פתיחת COM, CRC, timeouts, callbacks ושגיאות. שימושי לאיתור תקלה בזמן.</p></article>
<article class="panel"><h3>Structured report</h3><p>JSON או CSV עם מדדים מסוכמים שאפשר להשוות, לצייר ולבדוק אוטומטית.</p></article></div></section>
<section><h2>למה snapshot?</h2><p>ה-HTML הזה נשמר בתיקייה בעלת timestamp ומכיל את המספרים וההסברים כפי שהיו בזמן יצירתו. עם זאת, המודלים וקובצי המקור עצמם עדיין שייכים ל-pipeline הנוכחי. מערכת model runs מלאה, שתשמור גם artifacts נפרדים לכל ניסוי, היא שלב עתידי.</p></section>
"""
    return page("files.html", "מקורות המידע", "מאיזה קובץ הגיע כל חלק בדוח", body, report_id)


def build_index_page(context: dict[str, Any], report_id: str) -> str:
    records = context["records"]
    validation = context["validation"]
    float_report = context["float_report"]
    quant = context["quant_report"]
    hil = context["hil_report"]
    sessions = len({str(row.get("session_id", "unknown")) for row in records})
    test_accuracy = float_report.get("test_macro_accuracy")
    per_class = float_report.get("test_per_class_accuracy", {})
    weakest = min(per_class.items(), key=lambda item: item[1]) if per_class else None
    statuses = []
    statuses.append(badge(
        "good" if validation.get("status") == "valid" else "warn" if validation else "bad",
        "Dataset validation",
        f"{len(records)} פריימים, {sessions} sessions; מצב: {validation.get('status', 'לא זמין')}",
    ))
    statuses.append(badge(
        "good" if test_accuracy is not None and test_accuracy >= 0.80 else "warn" if test_accuracy is not None else "bad",
        "Model quality",
        f"Macro test accuracy {fmt_percent(test_accuracy)}" +
        (f"; המחלקה החלשה: {weakest[0]} {fmt_percent(weakest[1])}" if weakest else ""),
    ))
    drop = quant.get("quantization_accuracy_drop")
    statuses.append(badge(
        "good" if drop is not None and drop <= 0.05 else "warn" if drop is not None else "bad",
        "Quantization",
        f"Accuracy drop: {fmt_percent(drop)}; model: {quant.get('model_size_bytes', 'לא זמין')} bytes",
    ))
    hil_result = str(hil.get("result", "לא זמין"))
    statuses.append(badge(
        "good" if hil_result == "pass" else "bad" if hil_result == "fail" else "warn",
        "NPU / HIL",
        f"הדוח המובנה הנוכחי: {hil_result}",
    ))
    cards = "".join((
        metric_card("Raw frames", str(len(records)), "כל ה-labels"),
        metric_card("Sessions", str(sessions), "גיוון עצמאי"),
        metric_card("Float macro", fmt_percent(test_accuracy), "held-out test"),
        metric_card("INT8 macro", fmt_percent(quant.get("test_macro_accuracy")), "TFLite test"),
    ))
    body = f"""
<section class="hero-grid">{cards}</section>
<section><h2>תמונת מצב</h2><div class="status-list">{''.join(statuses)}</div></section>
{notice("info", "המסקנה החשובה", "איכות המודל, איכות ה-quantization ונאמנות ה-NPU הן שלוש שאלות נפרדות. דוח ירוק ב-HIL אינו מחליף test מול labels.")}
<section><h2>מסלול קריאה מומלץ</h2>
<ol class="steps"><li><a href="dataset.html">הנתונים</a> — האם יש מספיק sessions ו-bursts?</li><li><a href="training.html">האימון</a> — היכן המודל טועה והאם הוא משנן?</li><li><a href="predictions.html">הפריימים</a> — לראות את הקלט והתשובה לכל sample.</li><li><a href="quantization.html">Quantization</a> — האם INT8 שינה את המודל?</li><li><a href="npu_hil.html">NPU / HIL</a> — האם הלוח נאמן ל-TFLite?</li></ol></section>
<section><h2>מה הדוח הזה שינה?</h2><p>רק נוצרה תיקיית HTML חדשה. Raw data, prepared data, state, Keras, TFLite, generated NPU code וה-firmware לא שונו.</p></section>
"""
    return page("index.html", "סקירת מערכת הלמידה", "הסבר אנושי לכל שלב ולכל מדד", body, report_id)


REPORT_CSS = r"""
:root{--bg:#07111f;--panel:#0d1b2d;--panel2:#11243a;--text:#e8f0f8;--muted:#9bb0c4;--line:#243a52;--blue:#38bdf8;--green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--radius:18px}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0,#12395a 0,transparent 32rem),var(--bg);color:var(--text);font-family:"Segoe UI",Arial,sans-serif;line-height:1.65}.topbar{max-width:1280px;margin:auto;padding:38px 28px 20px;display:flex;justify-content:space-between;gap:24px;align-items:end}.topbar h1{font-size:clamp(2rem,5vw,3.8rem);line-height:1.05;margin:.15em 0}.topbar p{color:var(--muted);margin:0}.eyebrow{color:var(--blue);font-weight:800;letter-spacing:.15em;font-size:.75rem}.run-id{direction:ltr;text-align:left;background:#07101dcc;border:1px solid var(--line);border-radius:14px;padding:12px 16px}.run-id span{display:block;color:var(--muted);font-size:.72rem}.run-id code{color:#c4eaff}nav{position:sticky;top:0;z-index:20;display:flex;gap:6px;overflow:auto;padding:10px max(20px,calc((100vw - 1224px)/2));background:#07111fe6;border-block:1px solid var(--line);backdrop-filter:blur(14px)}nav a{white-space:nowrap;color:var(--muted);text-decoration:none;padding:8px 13px;border-radius:10px}nav a:hover,nav a.active{background:var(--panel2);color:#fff}main{max-width:1280px;margin:auto;padding:28px}section{margin:0 0 34px}h2{font-size:1.55rem;margin:0 0 15px}h3{margin:.2em 0}a{color:#7dd3fc}.hero-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.metric,.panel,.status-card,.prediction-card,.filters,.notice{background:linear-gradient(145deg,#102238e8,#0b1829e8);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 14px 36px #0003}.metric{padding:18px}.metric span,.metric small{display:block;color:var(--muted)}.metric strong{display:block;font-size:1.8rem;direction:ltr;text-align:right;margin:.15em 0}.status-list{display:grid;gap:12px}.status-card{display:flex;align-items:center;gap:16px;padding:16px}.status-card p{margin:0;color:var(--muted)}.status-dot{width:14px;height:14px;border-radius:50%;flex:none;box-shadow:0 0 18px currentColor}.good .status-dot{background:var(--green);color:var(--green)}.warn .status-dot{background:var(--yellow);color:var(--yellow)}.bad .status-dot{background:var(--red);color:var(--red)}.notice{padding:16px 18px;margin:14px 0;border-right:5px solid var(--blue)}.notice p{margin:.25em 0 0;color:#cbd8e5}.notice.warn{border-right-color:var(--yellow)}.notice.bad{border-right-color:var(--red)}.notice.good{border-right-color:var(--green)}.two-column{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.panel{padding:20px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:16px}table{width:100%;border-collapse:collapse;background:#0b192a}th,td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}thead{background:#132840;color:#dff4ff}tbody tr:hover{background:#14263a}.confusion th,.confusion td{text-align:center}.confusion td strong,.confusion td small{display:block}.confusion td small{color:#dbeafe}.explain,.muted{color:var(--muted)}.block{display:block;direction:ltr;text-align:left;white-space:pre-wrap;background:#05101d;border:1px solid var(--line);padding:16px;border-radius:12px}.chart{width:100%;height:330px;background:#0a1727;border:1px solid var(--line);border-radius:16px}.glossary{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:15px}.glossary p{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:13px;margin:0}.filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;padding:16px;margin-bottom:18px}.filters label{color:var(--muted);font-size:.85rem}.filters select,.filters input{width:100%;margin-top:5px;background:#07111f;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:9px}.filters output{display:block;color:#fff}.visible-count{font-weight:700}.prediction-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}.prediction-card{overflow:hidden}.prediction-card.wrong{border-color:#7f1d1d}.prediction-card.correct{border-color:#14532d}.prediction-images{display:grid;grid-template-columns:1fr 1fr;background:#02060b}.prediction-images figure{margin:0;min-width:0}.prediction-images img{display:block;width:100%;height:220px;object-fit:contain;image-rendering:pixelated}.prediction-images figcaption{text-align:center;color:var(--muted);font-size:.75rem;padding:4px}.prediction-info{padding:16px}.prediction-info h3 span{color:var(--muted);font-size:.75rem}.prediction-answer{font-size:1.25rem}.result-pill{float:left;background:#334155;padding:3px 9px;border-radius:999px}.wrong .result-pill{background:#7f1d1d}.correct .result-pill{background:#14532d}.scores{display:flex;flex-wrap:wrap;gap:5px}.score{background:#07111f;border:1px solid var(--line);padding:4px 7px;border-radius:8px;font-size:.72rem}.steps{display:grid;gap:12px}.steps li{background:var(--panel);border:1px solid var(--line);padding:14px 18px;border-radius:13px}details{margin-top:12px;color:var(--muted)}footer{border-top:1px solid var(--line);color:var(--muted);padding:25px;text-align:center}@media(max-width:700px){.topbar{display:block;padding-top:24px}.run-id{margin-top:18px}.prediction-grid{grid-template-columns:1fr}.prediction-images img{height:170px}main{padding:18px}}
"""


REPORT_JS = r"""
function renderAllCharts(){if(!window.reportCharts)return;document.querySelectorAll('canvas[data-chart]').forEach(canvas=>drawChart(canvas,window.reportCharts[canvas.dataset.chart]));}
function drawChart(canvas,data){if(!data||!data.labels||!data.labels.length){canvas.outerHTML='<p class="notice warn">אין training_history.csv זמין לציור.</p>';return;}const ratio=window.devicePixelRatio||1,w=canvas.clientWidth||900,h=330;canvas.width=w*ratio;canvas.height=h*ratio;const c=canvas.getContext('2d');c.scale(ratio,ratio);c.clearRect(0,0,w,h);const pad={r:28,l:58,t:38,b:45};let values=data.series.flatMap(s=>s.values).filter(v=>Number.isFinite(v));let min=data.percent?0:Math.min(...values),max=data.percent?1:Math.max(...values);if(max===min)max=min+1;const x=i=>pad.l+i*(w-pad.l-pad.r)/Math.max(1,data.labels.length-1),y=v=>pad.t+(max-v)*(h-pad.t-pad.b)/(max-min);c.strokeStyle='#29415a';c.fillStyle='#9bb0c4';c.font='12px Segoe UI';for(let i=0;i<=5;i++){let v=min+(max-min)*i/5,py=y(v);c.beginPath();c.moveTo(pad.l,py);c.lineTo(w-pad.r,py);c.stroke();c.fillText(data.percent?Math.round(v*100)+'%':v.toFixed(2),7,py+4);}data.series.forEach((s,si)=>{c.strokeStyle=s.color;c.lineWidth=2.5;c.beginPath();s.values.forEach((v,i)=>{if(!Number.isFinite(v))return;i?c.lineTo(x(i),y(v)):c.moveTo(x(i),y(v));});c.stroke();c.fillStyle=s.color;c.fillRect(pad.l+si*180,pad.t-25,14,4);c.fillStyle='#dce8f3';c.fillText(s.name,pad.l+20+si*180,pad.t-18);});c.fillStyle='#9bb0c4';const step=Math.max(1,Math.ceil(data.labels.length/8));data.labels.forEach((label,i)=>{if(i%step===0||i===data.labels.length-1)c.fillText(String(label),x(i)-4,h-18);});}
function setupPredictionFilters(){const ids=['label','prediction','split','result','agreement'];const controls=Object.fromEntries(ids.map(id=>[id,document.getElementById('filter-'+id)]));const confidence=document.getElementById('filter-confidence'),output=document.getElementById('confidence-output'),cards=[...document.querySelectorAll('.prediction-card')],count=document.getElementById('visible-count');function apply(){let limit=Number(confidence.value)/100;output.value=confidence.value+'%';let visible=0;cards.forEach(card=>{let ok=ids.every(id=>controls[id].value==='all'||card.dataset[id]===controls[id].value);let value=Number(card.dataset.confidence);if(Number.isFinite(value)&&value>=0)ok=ok&&value<=limit;card.hidden=!ok;if(ok)visible++;});count.textContent='מוצגים '+visible+' מתוך '+cards.length+' פריימים';}Object.values(controls).forEach(control=>control.addEventListener('change',apply));confidence.addEventListener('input',apply);apply();}
window.addEventListener('resize',()=>{clearTimeout(window.__chartTimer);window.__chartTimer=setTimeout(renderAllCharts,120);});
"""


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


class LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str,
                        attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        key = "src" if tag in ("img", "script") else "href" if tag in ("a", "link") else None
        if key and attributes.get(key):
            self.references.append(str(attributes[key]))


def validate_generated_report(report_dir: Path, expected_records: int) -> None:
    """Fail generation if a local report page or visible asset is broken."""
    errors: list[str] = []
    for filename, _ in PAGES:
        path = report_dir / filename
        if not path.exists():
            errors.append(f"missing page: {filename}")
            continue
        content = path.read_text(encoding="utf-8")
        if '<html lang="he" dir="rtl">' not in content:
            errors.append(f"missing Hebrew RTL root: {filename}")
        parser = LocalAssetParser()
        parser.feed(content)
        for reference in parser.references:
            parsed = urlparse(reference)
            if parsed.scheme or reference.startswith(("#", "javascript:")):
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            # Source-file links may deliberately describe a missing pipeline
            # artifact. Pages, styles, scripts and visible images may not.
            if target.suffix.lower() in {
                ".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg"
            } and not target.exists():
                errors.append(f"broken local reference in {filename}: {reference}")
    predictions = (report_dir / "predictions.html").read_text(encoding="utf-8")
    card_count = predictions.count('class="prediction-card ')
    if card_count != expected_records:
        errors.append(
            f"prediction gallery has {card_count} cards, expected {expected_records}"
        )
    if errors:
        raise RuntimeError("Generated HTML validation failed: " + "; ".join(errors))


def create_report(skip_inference: bool) -> Path:
    records, metadata_files = discover_metadata()
    split_map = prepared_split_map()
    records, inference = enrich_and_infer(records, split_map, skip_inference)
    model_hash = (sha256_file(MODELS_ROOT / "rps_int8.tflite")[:8]
                  if (MODELS_ROOT / "rps_int8.tflite").exists() else "no-model")
    base_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"__{model_hash}"
    report_root = REPORTS_ROOT / "html"
    report_id = base_id
    suffix = 1
    while (report_root / report_id).exists():
        suffix += 1
        report_id = f"{base_id}_{suffix}"
    report_dir = report_root / report_id
    report_dir.mkdir(parents=True, exist_ok=False)

    known_sources = [
        (REPORTS_ROOT / "dataset_validation.json", "בדיקת שלמות ואיכות ה-dataset"),
        (PREPARED_ROOT / "manifest.json", "חלוקת train/validation/test וחוזה preprocessing"),
        (REPORTS_ROOT / "training_history.csv", "Accuracy ו-loss לכל epoch"),
        (REPORTS_ROOT / "float_model_evaluation.json", "הערכת מודל Keras ו-confusion matrix"),
        (REPORTS_ROOT / "quantized_model_evaluation.json", "הערכת TFLite INT8 וחוזה tensors"),
        (REPORTS_ROOT / "hil_validation.json", "השוואת host TFLite מול Neural-ART"),
        (MODELS_ROOT / "model_contract.json", "ABI של המודל המשולב"),
        (MODELS_ROOT / "rps_float.keras", "מודל Keras float"),
        (MODELS_ROOT / "rps_int8.tflite", "המודל הכמותי המיועד ל-NPU"),
        (CONFIG_ROOT / "training.json", "הגדרות אימון ו-quality gates"),
        (CONFIG_ROOT / "preprocessing.json", "חוזה עיבוד עומק ל-64×50"),
        (REVIEW_PATH, "החלטות ביקורת אנושית: accept/reject/relabel"),
    ]
    known_sources.extend((path, "Metadata שורה-לכל-פריים") for path in metadata_files)
    sources = [source_info(path, description, report_dir) for path, description in known_sources]
    context = {
        "classes": class_names(),
        "records": records,
        "inference": inference,
        "validation": read_json(REPORTS_ROOT / "dataset_validation.json"),
        "prepared_manifest": read_json(PREPARED_ROOT / "manifest.json"),
        "float_report": read_json(REPORTS_ROOT / "float_model_evaluation.json"),
        "quant_report": read_json(REPORTS_ROOT / "quantized_model_evaluation.json"),
        "hil_report": read_json(REPORTS_ROOT / "hil_validation.json"),
        "history": read_history(),
        "sources": sources,
    }
    pages = {
        "index.html": build_index_page(context, report_id),
        "dataset.html": build_dataset_page(context, report_id),
        "training.html": build_training_page(context, report_id),
        "predictions.html": build_predictions_page(context, report_id, report_dir),
        "quantization.html": build_quantization_page(context, report_id),
        "npu_hil.html": build_hil_page(context, report_id),
        "files.html": build_files_page(context, report_id),
    }
    write_text(report_dir / "report.css", REPORT_CSS)
    write_text(report_dir / "report.js", REPORT_JS)
    for filename, contents in pages.items():
        write_text(report_dir / filename, contents)
    manifest = {
        "schema": 1,
        "created_utc": utc_now(),
        "report_id": report_id,
        "records": len(records),
        "inference": inference,
        "pages": list(pages),
        "sources": sources,
        "note": ("This is an analysis snapshot of current pipeline artifacts, "
                 "not yet an immutable model-training run."),
    }
    write_text(report_dir / "analysis_manifest.json",
               json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    validate_generated_report(report_dir, len(records))
    latest = f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={quote(report_id)}/index.html">
<title>N6 latest training analysis</title></head><body>
<p>הדוח האחרון: <a href="{quote(report_id)}/index.html">{esc(report_id)}</a></p></body></html>"""
    write_text(report_root / "latest.html", latest)
    return report_dir / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true",
                        help="Open the generated index in the default browser")
    parser.add_argument("--skip-inference", action="store_true",
                        help="Generate a faster report without loading Keras/TFLite")
    args = parser.parse_args()
    index = create_report(args.skip_inference)
    print(f"[DONE] Interactive report: {index}")
    print(f"[INFO] Latest shortcut: {REPORTS_ROOT / 'html' / 'latest.html'}")
    if args.open:
        webbrowser.open(index.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
