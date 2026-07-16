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

""" S3 API Credentials Configuration Model """

import secrets
import string
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, SecretStr, ConfigDict


def generate_access_key_id(project_id: int) -> str:
    """
    Generate an S3-style access key ID.

    Format: ELITEA + project_id padded + random chars
    Total length: 20 characters (AWS standard)
    """
    prefix = f"ELITEA{int(project_id):06d}"
    remaining = 20 - len(prefix)
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(chars) for _ in range(remaining))
    return prefix + suffix


def generate_secret_access_key() -> str:
    """
    Generate an S3-style secret access key.

    Length: 40 characters (AWS standard)
    """
    chars = string.ascii_letters + string.digits + '+/'
    return ''.join(secrets.choice(chars) for _ in range(40))


class S3ApiCredentialsConfig(BaseModel):
    """
    S3 API Credentials configuration model.

    Stored as a configuration item, visible in the Configurations UI.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "metadata": {
                "label": "S3 API Credentials",
                "section": "credentials",
                "categories": ["storage"],
                "icon_url": "s3credentials.svg",
                "type": "s3_api_credentials",
            }
        }
    )

    access_key_id: str = Field(..., description="S3 Access Key ID (auto-generated)")
    secret_access_key: Optional[SecretStr] = Field(None, description="S3 Secret Access Key")
    user_id: int = Field(..., description="User who created the credential")
    expires_at: Optional[str] = Field(None, description="Expiration date (ISO format)")
    permissions: List[str] = Field(
        default_factory=list,
        description="Permitted S3 operations (empty = all)"
    )
    bucket_permissions: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Per-bucket permissions: {bucket_name: ['read', 'write']}. Empty = unrestricted."
    )
    is_active: bool = Field(default=True, description="Whether credential is active")

    @staticmethod
    def check_connection(data: dict) -> dict:
        """Validate credentials format"""
        access_key = data.get('access_key_id', '')
        if not access_key.startswith('ELITEA'):
            return {"success": False, "message": "Invalid access key format"}
        if len(access_key) != 20:
            return {"success": False, "message": "Access key must be 20 characters"}
        return {"success": True, "message": "Credentials format valid"}


# Configuration record for registering with configurations plugin
s3_api_credentials_configuration_record = dict(
    type_name='s3_api_credentials',
    section='credentials',
    model=S3ApiCredentialsConfig,
)
