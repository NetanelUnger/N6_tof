"""Strict classification contract and generated definitions for host/firmware."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from pathlib import Path

from project_context import digest, semantic_hash, validate_manifest

MAX_CLASSES = 16
PROFILES = {"rps_silhouette_v1": 0, "spatial_depth_v1": 1}


def identity(contract):
    fields = ("schema", "project_id", "project_semantics", "classes", "input_profile",
              "model_template", "input", "output", "preprocessing", "model_sha256")
    return digest({key: contract[key] for key in fields})


def validate(contract, *, manifest=None, model_path=None):
    if contract.get("schema") != 3 or contract.get("contract_version") != 1:
        raise ValueError("BLOCKED: incompatible model contract version.")
    classes = contract["classes"]
    if not 2 <= len(classes) <= MAX_CLASSES:
        raise ValueError("BLOCKED: unsupported classifier output count.")
    if [c["output_index"] for c in classes] != list(range(len(classes))):
        raise ValueError("BLOCKED: noncontiguous model output mapping.")
    if len({c["stable_id"] for c in classes}) != len(classes):
        raise ValueError("BLOCKED: duplicate class identity.")
    if contract["input_profile"] not in PROFILES:
        raise ValueError("BLOCKED: unsupported preprocessing profile.")
    inputs, output = contract["input"], contract["output"]
    if (inputs["shape"] != [1, 50, 64, 1] or inputs["dtype"] != "uint8" or
            inputs["scale"] != 1.0 or inputs["zero_point"] != 0):
        raise ValueError("BLOCKED: unsupported model input/quantization.")
    if (output["shape"] != [1, len(classes)] or output["dtype"] != "int8" or
            output["scale"] != 1.0 / 256.0 or output["zero_point"] != -128):
        raise ValueError("BLOCKED: unsupported model output/quantization.")
    if identity(contract) != contract.get("contract_sha256"):
        raise ValueError("BLOCKED: model contract hash mismatch.")
    if manifest:
        if (contract["project_id"] != manifest["project_id"] or
                contract["project_semantics"] != semantic_hash(manifest) or
                contract["classes"] != manifest["classes"] or
                contract["preprocessing"] != manifest["preprocessing"]):
            raise ValueError("BLOCKED: model belongs to another project/configuration.")
    if model_path:
        if hashlib.sha256(Path(model_path).read_bytes()).hexdigest() != contract["model_sha256"]:
            raise ValueError("BLOCKED: TFLite model does not match its contract.")
    return contract


def create(manifest, legacy_metrics, model_path):
    validate_manifest(manifest)
    contract = deepcopy(legacy_metrics)
    contract.update(schema=3, contract_version=1, project_id=manifest["project_id"],
        project_semantics=semantic_hash(manifest), classes=deepcopy(manifest["classes"]),
        input_profile=manifest["input_profile"], model_template=manifest["model_template"],
        preprocessing=deepcopy(manifest["preprocessing"]),
        model_sha256=hashlib.sha256(Path(model_path).read_bytes()).hexdigest())
    contract["contract_sha256"] = identity(contract)
    return validate(contract, manifest=manifest, model_path=model_path)


def c_string(value):
    # UTF-8 octal escapes are valid C even for supplementary Unicode characters.
    return '"' + ''.join(chr(b) if 32 <= b <= 126 and b not in (34, 92)
                         else f"\\{b:03o}" for b in value.encode("utf-8")) + '"'


def generate_header(contract):
    validate(contract)
    names = ", ".join(c_string(c["name"]) for c in contract["classes"])
    display = ", ".join(c_string(c.get("display_name", c["name"])) for c in contract["classes"])
    identifier = ", ".join(f"0x{x:02x}" for x in bytes.fromhex(contract["contract_sha256"]))
    pre = contract["preprocessing"]
    legacy = int(contract["input_profile"] == "rps_silhouette_v1" and
                 [c["name"] for c in contract["classes"]] == ["none", "rock", "paper", "scissors"])
    return f'''/* Generated from the validated project/model contract. */
#ifndef N6_MODEL_CONTRACT_H
#define N6_MODEL_CONTRACT_H
#define N6_MODEL_CONTRACT_VERSION (1U)
#define N6_MODEL_MAX_CLASSES ({MAX_CLASSES}U)
#define N6_MODEL_CLASS_COUNT ({len(contract['classes'])}U)
#define N6_MODEL_LEGACY_RPS ({legacy}U)
#define N6_MODEL_INPUT_WIDTH (64U)
#define N6_MODEL_INPUT_HEIGHT (50U)
#define N6_MODEL_INPUT_PROFILE ({PROFILES[contract['input_profile']]}U)
#define N6_MODEL_PROFILE_SILHOUETTE (0U)
#define N6_MODEL_PROFILE_SPATIAL_DEPTH (1U)
#define N6_MODEL_NEAR_MM ({int(pre['near_mm'])}U)
#define N6_MODEL_FAR_MM ({int(pre['far_mm'])}U)
#define N6_MODEL_INVALID_MM ({int(pre['invalid_mm'])}U)
#define N6_MODEL_CLASS_NAMES {{ {names} }}
#define N6_MODEL_CLASS_DISPLAY_NAMES {{ {display} }}
#define N6_MODEL_CONTRACT_SHA256 {c_string(contract['contract_sha256'])}
#define N6_MODEL_CONTRACT_BYTES {{ {identifier} }}
#define N6_MODEL_OUTPUT_ZERO_POINT (-128)
#define N6_MODEL_OUTPUT_SCALE_DENOMINATOR (256U)
#if N6_MODEL_CLASS_COUNT < 2 || N6_MODEL_CLASS_COUNT > N6_MODEL_MAX_CLASSES
#error "Unsupported classification contract"
#endif
#endif
'''
