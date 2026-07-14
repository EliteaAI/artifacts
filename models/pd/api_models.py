from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field


class BucketCreateRequest(BaseModel):
    name: str = Field(..., description="Bucket name (letters, numbers, hyphens; must start with a letter)")
    expiration_measure: Optional[str] = Field(None, description="Retention period unit: days, weeks, months, years")
    expiration_value: Optional[int] = Field(None, description="Retention period value")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "my-reports",
                    "expiration_measure": "months",
                    "expiration_value": 6
                }
            ]
        }
    )


class BucketUpdateRequest(BaseModel):
    name: str = Field(..., description="Bucket name to update retention policy for")
    expiration_measure: str = Field(..., description="Retention period unit: days, weeks, months, years")
    expiration_value: int = Field(..., description="Retention period value")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "my-reports",
                    "expiration_measure": "years",
                    "expiration_value": 1
                }
            ]
        }
    )


class BucketPatchRequest(BaseModel):
    is_pinned: Optional[bool] = Field(None, description="Whether the bucket is pinned")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "is_pinned": True
                }
            ]
        }
    )


class S3CredentialCreateRequest(BaseModel):
    name: Optional[str] = Field("S3 Access Key", description="Display name for the credential")
    user_id: Optional[int] = Field(None, description="User ID to assign credential to (defaults to current user)")
    expires_in_days: Optional[int] = Field(None, description="Number of days until expiration (omit for no expiry)")
    permissions: Optional[List[str]] = Field(default_factory=list, description="Permitted S3 operations (empty = all)")
    bucket_permissions: Optional[Dict[str, List[str]]] = Field(
        default_factory=dict,
        description="Per-bucket permissions: {bucket_name: ['read', 'write']}. Empty = unrestricted."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "CI/CD pipeline key",
                    "expires_in_days": 365,
                    "permissions": []
                }
            ]
        }
    )

