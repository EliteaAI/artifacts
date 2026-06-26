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

""" Generic utility functions for artifacts plugin """

from typing import Tuple

from tools import VaultClient


# Default single-file upload limit when the vault secret is unset (MB).
DEFAULT_MAX_FILE_UPLOAD_SIZE_MB = 150


def extract_project_id(project):
    """
    Get the project id from either a dict (v2 path) or a Project ORM object
    (S3 route path). Returns None if neither shape is present.
    """
    if project is None:
        return None
    if isinstance(project, dict):
        return project.get('id')
    return getattr(project, 'id', None)


def get_max_upload_bytes(project_id) -> int:
    """
    Max single-file upload size in bytes.

    Shares the vault knob ``chat_max_file_upload_size_mb`` with the chat
    attachment path so one secret governs every upload route. Falls back to
    the default on any vault error so a vault hiccup never blocks uploads.
    """
    try:
        secrets = VaultClient(project_id).get_all_secrets()
        mb = int(secrets.get('chat_max_file_upload_size_mb', DEFAULT_MAX_FILE_UPLOAD_SIZE_MB))
    except Exception:  # pylint: disable=W0703
        mb = DEFAULT_MAX_FILE_UPLOAD_SIZE_MB
    return mb * 1024 * 1024


def parse_filepath(filepath: str) -> Tuple[str, str]:
    """
    Parse filepath into bucket and filename components.
    
    Args:
        filepath: File path in format /{bucket}/{filename} or {bucket}/{filename}
        
    Returns:
        Tuple of (bucket, filename)
        
    Raises:
        ValueError: If filepath format is invalid
    """
    # Remove leading slash if present
    path = filepath.lstrip('/')
    
    if '/' not in path:
        raise ValueError(f"Invalid filepath format: {filepath}. Expected /{'{bucket}'}/{'{filename}'}")
    
    # Split on first slash only - filename may contain additional slashes (folders)
    bucket, filename = path.split('/', 1)
    
    if not bucket or not filename:
        raise ValueError(f"Invalid filepath format: {filepath}. Bucket and filename required.")
    
    return bucket, filename


def make_filepath(bucket: str, filename: str) -> str:
    """
    Construct filepath from bucket and filename.
    
    Args:
        bucket: Bucket name
        filename: File name (may include folder path)
        
    Returns:
        Filepath string in format /{bucket}/{filename}
    """
    return f"/{bucket}/{filename}"



