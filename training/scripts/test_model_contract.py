from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from model_contract import create, generate_header, identity, validate
from project_context import ProjectService, read


class Contracts(unittest.TestCase):
    def test_two_and_four_output_contracts_and_incompatible_rejection(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(source / "config", root / "config")
            service = ProjectService(root)
            manifest = service.create("fixture", "Fixture")
            model = root / "model.tflite"
            model.write_bytes(b"contract-only synthetic model hash fixture")
            for count in (2, 4):
                selected = deepcopy(manifest)
                selected["classes"] = selected["classes"][:count]
                metrics = {"input": {"dtype": "uint8", "shape": [1, 50, 64, 1], "scale": 1.0, "zero_point": 0},
                    "output": {"dtype": "int8", "shape": [1, count], "scale": 1/256, "zero_point": -128}}
                contract = create(selected, metrics, model)
                header = generate_header(contract)
                self.assertIn(f"#define N6_MODEL_CLASS_COUNT ({count}U)", header)
                self.assertEqual([c["output_index"] for c in contract["classes"]], list(range(count)))
                self.assertEqual(contract["contract_sha256"], identity(contract))
                for mutate in (lambda c: c.update(contract_version=99),
                               lambda c: c["output"].update(shape=[1, count+1]),
                               lambda c: c["input"].update(scale=0.5),
                               lambda c: c.update(model_sha256="0"*64)):
                    incompatible = deepcopy(contract)
                    mutate(incompatible)
                    with self.assertRaises(ValueError):
                        validate(incompatible, manifest=selected, model_path=model)
                other = deepcopy(selected)
                other["project_id"] = "another-project"
                with self.assertRaises(ValueError):
                    validate(contract, manifest=other, model_path=model)


if __name__ == "__main__":
    unittest.main()
