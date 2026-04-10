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



