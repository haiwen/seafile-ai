import importlib.util
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location(
    'test_file_tools', str(PROJECT_ROOT / 'test_file_tools.py')
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

suite = unittest.TestLoader().loadTestsFromTestCase(mod.ListFilesTest)
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
