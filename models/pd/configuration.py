from typing import Optional

from pydantic import BaseModel, SecretStr, ConfigDict
import boto3


class S3Config(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "metadata": {
                "label": "S3 Storage",
                "section": "storage",
                "icon_url": "s3storage.svg",
                "type": "s3",
            }
        }
    )

    access_key: Optional[str] = None
    secret_access_key: Optional[SecretStr] = None
    region_name: str
    use_compatible_storage: bool = False
    storage_url: str

    @staticmethod
    def check_connection(data: dict) -> dict:
        try:
            aws_kwargs = {
                'aws_access_key_id': data['access_key'],
                'aws_secret_access_key': data['secret_access_key'],
                'region_name': data['region_name']
            }
            if data.get('use_compatible_storage') and data.get('storage_url'):
                aws_kwargs['endpoint_url'] = data['storage_url']
            s3 = boto3.client('s3', **aws_kwargs)
            s3.list_buckets()
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "message": str(e)}


configuration_record = dict(
    type_name='s3',
    section='storage',
    model=S3Config,
)