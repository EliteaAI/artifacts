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

""" S3 API Utility Functions """

import mimetypes
from urllib.parse import unquote


def parse_bucket_and_key(path: str) -> tuple:
    """
    Parse bucket name and key from S3 path.

    Path format: /{bucket}/{key}
    Returns: (bucket, key) tuple
    """
    # Remove leading slash
    path = path.lstrip('/')

    if '/' not in path:
        return path, ''

    parts = path.split('/', 1)
    bucket = parts[0]
    key = unquote(parts[1]) if len(parts) > 1 else ''

    return bucket, key


def guess_content_type(filename: str) -> str:
    """
    Guess the content type from filename.

    Returns application/octet-stream if unknown.
    """
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or 'application/octet-stream'


def format_http_date(dt) -> str:
    """
    Format datetime as HTTP date (RFC 7231).

    Example: Wed, 21 Oct 2015 07:28:00 GMT
    """
    from datetime import datetime
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    return dt.strftime('%a, %d %b %Y %H:%M:%S GMT')


def validate_bucket_name(name: str) -> tuple:
    """
    Validate S3 bucket name according to AWS rules.

    Returns: (is_valid, error_message)
    """
    import re

    if not name:
        return False, "Bucket name cannot be empty"

    if len(name) < 3 or len(name) > 63:
        return False, "Bucket name must be between 3 and 63 characters"

    # Must start and end with letter or number
    if not re.match(r'^[a-z0-9]', name) or not re.match(r'.*[a-z0-9]$', name):
        return False, "Bucket name must start and end with a letter or number"

    # Only lowercase letters, numbers, and hyphens
    if not re.match(r'^[a-z0-9-]+$', name):
        return False, "Bucket name can only contain lowercase letters, numbers, and hyphens"

    # Cannot have consecutive hyphens
    if '--' in name:
        return False, "Bucket name cannot have consecutive hyphens"

    # Cannot be formatted as IP address
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', name):
        return False, "Bucket name cannot be formatted as IP address"

    return True, None


def validate_object_key(key: str) -> tuple:
    """
    Validate S3 object key.

    Returns: (is_valid, error_message)
    """
    if not key:
        return False, "Object key cannot be empty"

    if len(key) > 1024:
        return False, "Object key cannot exceed 1024 characters"

    # Check for invalid characters (control characters except certain ones)
    for char in key:
        if ord(char) < 32 and char not in '\t\n\r':
            return False, f"Object key contains invalid character: {repr(char)}"

    return True, None


def get_part_range(range_header: str, total_size: int) -> tuple:
    """
    Parse Range header and return start/end bytes.

    Range header format: bytes=start-end

    Returns: (start, end) or (None, None) if invalid
    """
    if not range_header:
        return 0, total_size - 1

    if not range_header.startswith('bytes='):
        return None, None

    try:
        range_spec = range_header[6:]  # Remove 'bytes='
        parts = range_spec.split('-')

        if len(parts) != 2:
            return None, None

        start_str, end_str = parts

        if start_str == '':
            # Suffix range: -500 means last 500 bytes
            suffix_length = int(end_str)
            start = max(0, total_size - suffix_length)
            end = total_size - 1
        elif end_str == '':
            # Open-ended range: 500- means from byte 500 to end
            start = int(start_str)
            end = total_size - 1
        else:
            start = int(start_str)
            end = int(end_str)

        # Validate range
        if start < 0 or end >= total_size or start > end:
            return None, None

        return start, end

    except (ValueError, IndexError):
        return None, None
