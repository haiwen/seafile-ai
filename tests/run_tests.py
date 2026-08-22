import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT), pattern='test_*.py')
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
