"""Stage 05: train or resume a small CPU-friendly ToF classifier."""

from __future__ import annotations

import argparse
import csv
import os
import random

import numpy as np

from common import (CONFIG_ROOT, MODELS_ROOT, PREPARED_ROOT, REPORTS_ROOT,
                    atomic_json, class_names, file_fingerprint, load_json,
                    is_stage_current, mark_stage, relative, stable_hash, utc_now)


def load_split(name: str) -> tuple[np.ndarray, np.ndarray]:
    with np.load(PREPARED_ROOT / f"{name}.npz", allow_pickle=False) as archive:
        return archive["x"], archive["y"]


def build_model(tf, input_shape: tuple[int, int, int], classes: int,
                learning_rate: float):
    # Flatten keeps the spatial arrangement of fingers. GlobalAveragePooling
    # made the previous network unusually good at measuring total blob area,
    # but nearly blind to whether that area contained zero, two or five fingers.
    # All inference operations remain integer-friendly for Neural-ART.
    inputs = tf.keras.Input(shape=input_shape, dtype=tf.uint8, name="tof_u8")
    x = tf.keras.layers.Rescaling(1.0 / 255.0, name="to_float")(inputs)
    x = tf.keras.layers.Conv2D(16, 3, padding="same", activation="relu",
                               name="conv1")(x)
    x = tf.keras.layers.MaxPooling2D(2, name="pool1")(x)
    x = tf.keras.layers.Conv2D(24, 3, padding="same", activation="relu",
                               name="conv2")(x)
    x = tf.keras.layers.MaxPooling2D(2, name="pool2")(x)
    x = tf.keras.layers.Conv2D(32, 3, padding="same", activation="relu",
                               name="conv3")(x)
    x = tf.keras.layers.MaxPooling2D(2, name="pool3")(x)
    x = tf.keras.layers.Conv2D(24, 3, padding="same", activation="relu",
                               name="conv4")(x)
    x = tf.keras.layers.Flatten(name="preserve_spatial_layout")(x)
    x = tf.keras.layers.Dense(32, activation="relu", name="spatial_features")(x)
    x = tf.keras.layers.Dropout(0.25, name="training_dropout")(x)
    outputs = tf.keras.layers.Dense(classes, activation="softmax",
                                    name="gesture")(x)
    model = tf.keras.Model(inputs, outputs, name="rps_tof_classifier")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
        weighted_metrics=[
            tf.keras.metrics.SparseCategoricalAccuracy(
                name="balanced_accuracy"
            )
        ],
    )
    return model


def augment_training_set(x: np.ndarray, y: np.ndarray, config: dict,
                         seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Add deterministic, label-preserving ToF variations to training only."""
    copies = int(config.get("copies_per_sample", 0))
    if copies <= 0:
        return x, y
    rng = np.random.default_rng(seed)
    maximum_shift = int(config["maximum_translation_pixels"])
    generated_x = [x]
    generated_y = [y]
    for _ in range(copies):
        batch = np.zeros_like(x)
        for index, source in enumerate(x):
            image = source[..., 0]
            if rng.random() < float(config["horizontal_flip_probability"]):
                image = np.fliplr(image)
            row_shift = int(rng.integers(-maximum_shift, maximum_shift + 1))
            column_shift = int(rng.integers(-maximum_shift, maximum_shift + 1))
            translated = np.zeros_like(image)
            source_top = max(0, -row_shift)
            source_bottom = min(image.shape[0], image.shape[0] - row_shift)
            source_left = max(0, -column_shift)
            source_right = min(image.shape[1], image.shape[1] - column_shift)
            target_top = source_top + row_shift
            target_bottom = source_bottom + row_shift
            target_left = source_left + column_shift
            target_right = source_right + column_shift
            if source_top < source_bottom and source_left < source_right:
                translated[target_top:target_bottom, target_left:target_right] = (
                    image[source_top:source_bottom, source_left:source_right]
                )
            scale = rng.uniform(float(config["intensity_scale_min"]),
                                float(config["intensity_scale_max"]))
            nonzero = translated != 0
            adjusted = translated.astype(np.float32)
            adjusted[nonzero] *= scale
            adjusted[nonzero] = np.clip(adjusted[nonzero], 1, 255)
            batch[index, ..., 0] = np.rint(adjusted).astype(np.uint8)
        generated_x.append(batch)
        generated_y.append(y.copy())
    return np.concatenate(generated_x), np.concatenate(generated_y)


class EpochStateCallback:
    def __init__(self, tf, state_path, config_hash):
        self.callback = self._make(tf, state_path, config_hash)

    @staticmethod
    def _make(tf, state_path, config_hash):
        class Callback(tf.keras.callbacks.Callback):
            def on_epoch_end(self, epoch, logs=None):
                atomic_json(state_path, {
                    "schema": 1,
                    "updated_utc": utc_now(),
                    "config_hash": config_hash,
                    "completed_epochs": epoch + 1,
                    "metrics": {key: float(value)
                                for key, value in (logs or {}).items()},
                })
        return Callback()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Discard compatible checkpoint and start anew")
    args = parser.parse_args()
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    config = load_json(CONFIG_ROOT / "training.json")
    manifest = load_json(PREPARED_ROOT / "manifest.json")
    minimum_split = config["minimum_samples_per_split_per_class"]
    weak_splits = []
    for split in ("train", "validation", "test"):
        class_counts = manifest.get("counts", {}).get(split, {}).get("classes", {})
        for name in class_names():
            count = int(class_counts.get(name, 0))
            if count < minimum_split:
                weak_splits.append(f"{split}/{name}={count}")
    if weak_splits:
        raise RuntimeError(
            "Prepared data fails the per-class split quality gate "
            f"(minimum {minimum_split}): {', '.join(weak_splits)}. "
            "Capture more full bursts, then rerun stages 03 and 04."
        )
    config_hash = stable_hash({"training": config, "prepared": manifest})
    fingerprint = stable_hash({
        "config": config_hash,
        "splits": file_fingerprint(PREPARED_ROOT.glob("*.npz")),
    })
    final_model = MODELS_ROOT / "rps_float.keras"
    report_path = REPORTS_ROOT / "float_model_evaluation.json"
    history_path = REPORTS_ROOT / "training_history.csv"
    if (not args.force and
            is_stage_current("05_train", fingerprint,
                             [final_model, report_path, history_path])):
        print("Float model is current; reusing it. Pass --force to retrain.")
        return 0
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    tf.random.set_seed(config["seed"])
    x_train, y_train = load_split("train")
    x_validation, y_validation = load_split("validation")
    x_test, y_test = load_split("test")
    train_counts = np.bincount(y_train.astype(np.int64),
                               minlength=len(class_names()))
    if np.any(train_counts == 0):
        raise RuntimeError(
            f"Training split is missing a class: counts={train_counts.tolist()}"
        )
    # Preserve all measurements while preventing an oversized class (for
    # example 300 NONE versus 100 gestures) from dominating the loss.
    class_weights = {
        index: float(len(y_train) / (len(class_names()) * count))
        for index, count in enumerate(train_counts)
    }
    original_train_samples = len(y_train)
    x_train, y_train = augment_training_set(
        x_train, y_train, config.get("augmentation", {}), config["seed"]
    )
    print(f"Training augmentation: {original_train_samples} measured samples -> "
          f"{len(y_train)} samples; validation/test remain untouched.")
    validation_counts = np.bincount(
        y_validation.astype(np.int64), minlength=len(class_names())
    )
    validation_class_weights = len(y_validation) / (
        len(class_names()) * validation_counts
    )
    validation_sample_weights = validation_class_weights[
        y_validation.astype(np.int64)
    ].astype(np.float32)
    checkpoint = MODELS_ROOT / "rps_checkpoint.keras"
    epoch_state_path = MODELS_ROOT / "training_progress.json"
    initial_epoch = 0
    if not args.force and checkpoint.exists() and epoch_state_path.exists():
        progress = load_json(epoch_state_path)
        if progress.get("config_hash") == config_hash:
            model = tf.keras.models.load_model(checkpoint)
            initial_epoch = int(progress.get("completed_epochs", 0))
            print(f"Resuming the compatible checkpoint after epoch {initial_epoch}.")
        else:
            print("Checkpoint belongs to different data/config; starting a new model.")
            model = build_model(tf, tuple(x_train.shape[1:]), len(class_names()),
                                config["learning_rate"])
    else:
        model = build_model(tf, tuple(x_train.shape[1:]), len(class_names()),
                            config["learning_rate"])
    model.summary()
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            checkpoint, monitor="val_balanced_accuracy",
            mode="max", save_best_only=False),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_balanced_accuracy", mode="max",
            patience=config["early_stopping_patience"],
            restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", patience=3, factor=0.5, min_lr=1e-6),
        EpochStateCallback(tf, epoch_state_path, config_hash).callback,
    ]
    history = model.fit(
        x_train, y_train,
        validation_data=(x_validation, y_validation,
                         validation_sample_weights),
        epochs=config["epochs"], initial_epoch=initial_epoch,
        batch_size=config["batch_size"], callbacks=callbacks,
        class_weight=class_weights, verbose=2,
    )
    model.save(final_model)
    evaluation = model.evaluate(x_test, y_test, verbose=0, return_dict=True)
    probabilities = model.predict(x_test, verbose=0)
    test_predictions = np.argmax(probabilities, axis=1)
    per_class_accuracy = {}
    for index, name in enumerate(class_names()):
        mask = y_test == index
        per_class_accuracy[name] = float(
            np.mean(test_predictions[mask] == y_test[mask])
        )
    test_accuracy = float(np.mean(test_predictions == y_test))
    test_macro_accuracy = float(np.mean(list(per_class_accuracy.values())))
    confusion_matrix = np.zeros((len(class_names()), len(class_names())),
                                dtype=np.int64)
    for expected, predicted in zip(y_test.astype(np.int64), test_predictions):
        confusion_matrix[expected, predicted] += 1
    test_loss = float(evaluation["loss"])
    keys = sorted(history.history)
    with history_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", *keys])
        writer.writeheader()
        for index in range(len(next(iter(history.history.values()), []))):
            writer.writerow({"epoch": initial_epoch + index + 1,
                             **{key: history.history[key][index] for key in keys}})
    report = {
        "schema": 2, "created_utc": utc_now(),
        "test_loss": test_loss, "test_accuracy": test_accuracy,
        "test_macro_accuracy": test_macro_accuracy,
        "test_per_class_accuracy": per_class_accuracy,
        "model_parameters": int(model.count_params()),
        "classes": class_names(), "input_shape": list(x_train.shape[1:]),
        "input_dtype": "uint8", "config_hash": config_hash,
        "train_counts": train_counts.astype(int).tolist(),
        "measured_train_samples": original_train_samples,
        "augmented_train_samples": len(y_train),
        "confusion_matrix_rows_expected_columns_predicted": confusion_matrix.tolist(),
        "class_weights": {class_names()[index]: weight
                          for index, weight in class_weights.items()},
    }
    atomic_json(report_path, report)
    mark_stage("05_train", status="complete", inputs=fingerprint,
               outputs=[relative(final_model), relative(report_path),
                        relative(history_path)], details=report)
    print(f"Float model test accuracy: overall={test_accuracy:.3%}, "
          f"macro={test_macro_accuracy:.3%}, per-class={per_class_accuracy}")
    weak_classes = {
        name: accuracy for name, accuracy in per_class_accuracy.items()
        if accuracy < config.get("minimum_per_class_test_accuracy", 0.0)
    }
    if (test_macro_accuracy < config["minimum_test_accuracy"] or weak_classes):
        mark_stage("05_train", status="quality_gate_failed", inputs=fingerprint,
                   outputs=[relative(final_model), relative(report_path),
                            relative(history_path)], details=report)
        print(f"QUALITY GATE FAILED: required at least "
              f"{config['minimum_test_accuracy']:.1%} macro and "
              f"{config.get('minimum_per_class_test_accuracy', 0.0):.1%} "
              f"per class; weak classes={weak_classes}.")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
