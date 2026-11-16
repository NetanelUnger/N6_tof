"""Host-only checks: network retention must not weaken RAM settings guards."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

import guarded_ram

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Tools'))
import load_checked_ram


class RamNetworkTests(unittest.TestCase):
    def exercise(self, keep_network, failure=False, newline=b'\n'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inc = root / 'AppliNonSecure/Core/Inc'
            inc.mkdir(parents=True)
            update = root / 'Common/Update'
            update.mkdir(parents=True)
            files = {
                inc / 'app_features.h': b'#define APP_DEMO_BLE_ONLY (0U)' + newline,
                inc / 'w61_driver_config.h': b'#define W61_CONFIG_PRESERVE       (1)' + newline,
                inc / 'app_settings.h': b'#define APP_SETTINGS_WRITES_ENABLED 0U\n#define APP_SETTINGS_TRANSITION_ENABLED 0U\n',
                update / 'firmware_build_version.h': b'#define NATI_LAB_FIRMWARE_VERSION (44UL)\n',
            }
            debug = root / 'AppliNonSecure/Debug'
            debug.mkdir()
            for suffix in ('elf', 'bin', 'map'):
                files[debug / ('N6_AppliNonSecure.' + suffix)] = b'original-' + suffix.encode()
            for path, payload in files.items():
                path.write_bytes(payload)

            def build(*args, **kwargs):
                self.assertIn(b'(0U)' if keep_network else b'(1U)', (inc / 'app_features.h').read_bytes())
                self.assertIn(b'(1)', (inc / 'w61_driver_config.h').read_bytes())
                self.assertEqual((inc / 'app_settings.h').read_bytes(), files[inc / 'app_settings.h'])
                kwargs['stdout'].write('Non-Secure C heap capacity: 400000 bytes\n')
                for suffix in ('elf', 'bin', 'map'):
                    (debug / ('N6_AppliNonSecure.' + suffix)).write_bytes(b'new-' + suffix.encode())
                return type('Result', (), {'returncode': 1 if failure else 0})()

            with patch.object(guarded_ram, 'PROJECT_ROOT', root), patch.object(guarded_ram, 'GENERATED_ROOT', root / 'generated'), patch.object(guarded_ram.subprocess, 'run', side_effect=build):
                if failure:
                    with self.assertRaisesRegex(RuntimeError, 'build failed'):
                        guarded_ram.build_candidate(keep_network=keep_network)
                else:
                    result = guarded_ram.build_candidate(keep_network=keep_network)
                    self.assertEqual(result['ble_only'], not keep_network)
                    self.assertFalse(result['settings_writes'])
                    self.assertTrue(result['ncp_preserve'])
                    self.assertEqual(result['status'], 'BUILT')
                    self.assertEqual(Path(result['artifacts']['candidate.bin']['path']).read_bytes(), b'new-bin')
            for path, payload in files.items():
                self.assertEqual(path.read_bytes(), payload, str(path))

    def test_keep_network_lf(self):
        self.exercise(True)

    def test_keep_network_crlf(self):
        self.exercise(True, newline=b'\r\n')

    def test_default_ble_only(self):
        self.exercise(False)

    def test_failure_restores_originals(self):
        self.exercise(True, failure=True)


class CheckedLoadRouteTests(unittest.TestCase):
    def test_missing_identity_refuses_before_loader(self):
        with patch.object(load_checked_ram, 'execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'board-serial'):
                guarded_ram.load_candidate({'folder': '.', 'status': 'BUILT', 'heap': 379504})
            execute.assert_not_called()

    def test_stage_10_uses_checked_loader_without_replacing_debug(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            debug = folder / 'ordinary-debug.bin'
            debug.write_bytes(b'preserved')
            info = dict(folder=tmp, status='BUILT', heap=379504)
            manifest = folder / 'load-inputs/ram-load.json'
            with patch.object(load_checked_ram, 'save_manifest', return_value=manifest), \
                 patch.object(load_checked_ram, 'execute', return_value=dict(status='LOADED', target={})) as execute:
                result = guarded_ram.load_candidate(info, 'n6:test', 'board')
                execute.assert_called_once_with(manifest, folder / 'checked-load', 'board', 'n6:test')
            self.assertEqual(result['manifest'], str(manifest))
            self.assertEqual(debug.read_bytes(), b'preserved')
            self.assertEqual(json.loads((folder / 'load.json').read_text())['status'], 'LOADED')
            with self.assertRaisesRegex(RuntimeError, 'previous loader outcome'):
                guarded_ram.load_candidate(info, board_serial='board')

    def test_uncertain_failure_is_retained_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            info = dict(folder=tmp, status='BUILT', heap=379504)

            def failure(*args):
                (folder / 'checked-load').mkdir()
                (folder / 'checked-load/result.json').write_text(json.dumps({'status': 'UNCERTAIN'}))
                raise RuntimeError('lost debug link')

            with patch.object(load_checked_ram, 'save_manifest', return_value=folder / 'manifest.json'), \
                 patch.object(load_checked_ram, 'execute', side_effect=failure):
                with self.assertRaisesRegex(RuntimeError, 'lost debug link'):
                    guarded_ram.load_candidate(info, board_serial='board')
            self.assertEqual(json.loads((folder / 'load.json').read_text())['status'], 'UNCERTAIN')
            with self.assertRaisesRegex(RuntimeError, 'previous loader outcome'):
                guarded_ram.load_candidate(info, board_serial='board')


if __name__ == '__main__':
    unittest.main()
