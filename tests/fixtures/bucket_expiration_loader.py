"""Loads rpc/bucket_expiration.py as a real module for testing.

The module only imports `pylon.core.tools.{web,log}` and `tools.{MinioClient,
lifecycle_from_meta}`, both already stubbed by run_tests.install_stubs(), so
it can be loaded directly with no plugin-package scaffolding.
"""
import importlib.util
import sys
from pathlib import Path

ARTIFACTS_ROOT = Path(__file__).resolve().parent.parent.parent


def load_bucket_expiration():
    cached = sys.modules.get("artifacts_bucket_expiration")
    if cached is not None:
        return cached

    path = ARTIFACTS_ROOT / "rpc" / "bucket_expiration.py"
    spec = importlib.util.spec_from_file_location("artifacts_bucket_expiration", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["artifacts_bucket_expiration"] = module
    spec.loader.exec_module(module)
    return module
