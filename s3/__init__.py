# pylint: disable=C0116
#
#   Copyright 2026 EPAM Systems
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
S3-compatible API modules for Elitea Artifacts

This package contains:
- auth.py: AWS Signature V4 authentication
- responses.py: S3 XML response builders
- utils.py: Helper functions
- handlers/: Operation handlers (bucket, object, multipart)

Routes are defined in artifacts/routes/s3.py using Elitea's @web.route() pattern.
"""

from . import responses
from .auth import verify_s3_auth, s3_auth_required

__all__ = ['responses', 'verify_s3_auth', 's3_auth_required']
