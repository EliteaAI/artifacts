"""Utility functions for artifact ID handling."""
import base64
import re
from typing import Optional

from pylon.core.tools import log
from tools import MinioClient


class InvalidArtifactIdError(ValueError):
    """Raised when artifact_id has invalid pattern."""
    pass


def extract_path_from_artifact_id(artifact_id: str) -> tuple[str, str]:
    """
    Extract bucket name and filename from artifact_id.
    
    Artifact ID pattern: {type}_{bucket}_{timestamp}_{uuid8}_{ext}
    Example: img_mybucket_1703001234_a1b2c3d4_png
    
    Returns:
        tuple: (bucket_name, filename)
        Example: ('mybucket', 'img_mybucket_1703001234_a1b2c3d4.png')
    
    Raises:
        InvalidArtifactIdError: If artifact_id has invalid pattern
    """
    parts = artifact_id.split('_')
    
    # Must have at least 5 parts: type_bucket_timestamp_uuid_ext
    if len(parts) < 5:
        raise InvalidArtifactIdError(
            f"Invalid artifact_id pattern: must have at least 5 parts separated by underscore"
        )
    
    ext = parts[-1]  # Last part is extension
    
    # Bucket is everything between type and last three parts (timestamp_uuid_ext)
    bucket_name = '_'.join(parts[1:-3])
    
    if not bucket_name:
        raise InvalidArtifactIdError(
            f"Could not extract bucket name from artifact_id"
        )
    
    # Filename: everything except extension + .extension
    base = '_'.join(parts[:-1])
    filename = f"{base}.{ext}"
    
    return bucket_name, filename


def get_file_from_bucket(project, bucket: str, filename: str) -> Optional[bytes]:
    """
    Retrieve file content from MinIO bucket.
    
    Args:
        project: Project object from RPC
        bucket: Bucket name
        filename: Filename to retrieve
        
    Returns:
        File content as bytes, or None if not found
    """
    try:
        mc = MinioClient(project, configuration_title=None)
    except AttributeError as e:
        log.error(f"Error accessing storage: {e}")
        return None
    
    try:
        file_content = mc.download_file(bucket, filename)
        return file_content
    except Exception as e:
        log.debug(f"File {bucket}/{filename} not found in bucket: {e}")
        return None


def extract_base64_from_content(content) -> Optional[bytes]:
    """
    Extract base64-encoded file content from AttachmentMessageItem content field.
    
    Content structure:
    [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        {"type": "text", "text": "(artifact: ...)"}
    ]
    
    Args:
        content: Content field from AttachmentMessageItem (list of dicts)
        
    Returns:
        Decoded bytes if found, None otherwise
    """
    if not isinstance(content, list):
        return None
    
    for item in content:
        if item.get('type') == 'image_url':
            image_url = item.get('image_url', {}).get('url', '')
            if image_url.startswith('data:'):
                # Extract base64 part after "data:image/png;base64,"
                match = re.match(r'data:[^;]+;base64,(.+)', image_url)
                if match:
                    try:
                        return base64.b64decode(match.group(1))
                    except Exception:
                        return None
    
    return None


def validate_artifact_id(artifact_id: str) -> bool:
    """
    Validate artifact_id pattern.
    
    Valid pattern: {type}_{bucket}_{timestamp}_{uuid8}
    - type: 3 letters (img, doc, snd, vid, etc.)
    - bucket: any characters (no underscores recommended but allowed)
    - timestamp: numeric
    - uuid: 8 hex characters
    
    Args:
        artifact_id: Artifact identifier string
        
    Returns:
        True if valid pattern, False otherwise
    """
    parts = artifact_id.split('_')
    
    # Must have at least 4 parts
    if len(parts) < 4:
        return False
    
    # Type must be 3 letters
    artifact_type = parts[0]
    if len(artifact_type) != 3 or not artifact_type.isalpha():
        return False
    
    # Timestamp must be numeric
    timestamp = parts[-2]
    if not timestamp.isdigit():
        return False
    
    # UUID must be 8 hex characters
    uuid_part = parts[-1]
    if len(uuid_part) != 8:
        return False
    try:
        int(uuid_part, 16)  # Check if valid hex
    except ValueError:
        return False
    
    return True
