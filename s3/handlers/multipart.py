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

""" S3 Multipart Upload Operations Handler """

import uuid
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional
import xml.etree.ElementTree as ET


class _NoDTDTarget(ET.TreeBuilder):
    """TreeBuilder that rejects DOCTYPE/DTD to block XML entity-expansion bombs."""
    def doctype(self, name, pubid, system):
        raise ValueError("DTD/DOCTYPE is not allowed in request body")


def _safe_fromstring(data):
    return ET.fromstring(data, parser=ET.XMLParser(target=_NoDTDTarget()))
from flask import request, Response

from pylon.core.tools import log
from tools import MinioClient, context

from ..responses import (
    initiate_multipart_upload_response,
    upload_part_response,
    complete_multipart_upload_response,
    list_parts_response,
    delete_response,
    error_response
)


# Redis key prefix for multipart uploads
MULTIPART_PREFIX = 's3:multipart:'
MULTIPART_PART_PREFIX = 's3:multipart:part:'
MULTIPART_EXPIRE_SECONDS = 24 * 60 * 60  # 24 hours


class MultipartHandler:
    """Handler for S3 multipart upload operations"""

    def __init__(self, project, project_id: int = None, user_id: int = None):
        """
        Initialize the multipart handler with project context.

        Args:
            project: The project object for MinioClient
            project_id: Project ID for metadata
            user_id: User ID for metadata
        """
        self.project = project
        self.project_id = project_id or 0
        self.user_id = user_id or 0
        self.mc = MinioClient(project)

    @staticmethod
    def _get_redis():
        """Get Redis client from context"""
        try:
            from tools import config as c
            import redis
            return redis.Redis(
                host=c.REDIS_HOST,
                port=c.REDIS_PORT,
                password=c.REDIS_PASSWORD,
                db=0
            )
        except Exception as e:
            log.warning("Redis not available for multipart uploads: %s", e)
            return None

    @staticmethod
    def _get_upload_key(upload_id: str) -> str:
        """Get Redis key for upload metadata"""
        return f"{MULTIPART_PREFIX}{upload_id}"

    @staticmethod
    def _get_part_key(upload_id: str, part_number: int) -> str:
        """Get Redis key for part data"""
        return f"{MULTIPART_PART_PREFIX}{upload_id}:{part_number}"

    @staticmethod
    def _calculate_etag(data: bytes) -> str:
        """Calculate ETag (MD5 hash) for part"""
        return f'"{hashlib.md5(data).hexdigest()}"'

    def create_multipart_upload(self, bucket_name: str, key: str) -> Response:
        """
        Initiate a multipart upload.

        S3 Operation: POST /{bucket}/{key}?uploads

        Returns an upload ID to use for subsequent parts.
        """
        try:
            # Check if bucket exists
            existing_buckets = self.mc.list_bucket()
            if bucket_name not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Bucket {bucket_name} does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Generate upload ID
            upload_id = str(uuid.uuid4())

            # Store upload metadata in Redis
            redis_client = self._get_redis()
            if redis_client:
                upload_data = {
                    'bucket': bucket_name,
                    'key': key,
                    'project_id': self.project_id,
                    'user_id': self.user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'parts': {}
                }
                redis_client.setex(
                    self._get_upload_key(upload_id),
                    MULTIPART_EXPIRE_SECONDS,
                    json.dumps(upload_data)
                )
            else:
                # Fallback: store in memory (not recommended for production)
                log.warning("Redis not available, multipart state will be lost on restart")
                if not hasattr(context, '_multipart_uploads'):
                    context._multipart_uploads = {}
                context._multipart_uploads[upload_id] = {
                    'bucket': bucket_name,
                    'key': key,
                    'project_id': self.project_id,
                    'user_id': self.user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'parts': {}
                }

            return initiate_multipart_upload_response(
                bucket=bucket_name,
                key=key,
                upload_id=upload_id
            )

        except Exception as e:
            log.error("CreateMultipartUpload failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )

    def _get_upload_data(self, upload_id: str) -> Optional[Dict]:
        """Get upload metadata from Redis or memory"""
        redis_client = self._get_redis()
        if redis_client:
            data = redis_client.get(self._get_upload_key(upload_id))
            if data:
                return json.loads(data)
        else:
            if hasattr(context, '_multipart_uploads'):
                return context._multipart_uploads.get(upload_id)
        return None

    def _save_upload_data(self, upload_id: str, data: Dict):
        """Save upload metadata to Redis or memory"""
        redis_client = self._get_redis()
        if redis_client:
            redis_client.setex(
                self._get_upload_key(upload_id),
                MULTIPART_EXPIRE_SECONDS,
                json.dumps(data)
            )
        else:
            if not hasattr(context, '_multipart_uploads'):
                context._multipart_uploads = {}
            context._multipart_uploads[upload_id] = data

    def _delete_upload_data(self, upload_id: str, part_count: int = 0):
        """Delete upload metadata and parts from Redis or memory"""
        redis_client = self._get_redis()
        if redis_client:
            # Delete upload metadata
            redis_client.delete(self._get_upload_key(upload_id))
            # Delete all parts
            for i in range(1, part_count + 1):
                redis_client.delete(self._get_part_key(upload_id, i))
        else:
            if hasattr(context, '_multipart_uploads'):
                context._multipart_uploads.pop(upload_id, None)
            if hasattr(context, '_multipart_parts'):
                for i in range(1, part_count + 1):
                    context._multipart_parts.pop(f"{upload_id}:{i}", None)

    def upload_part(self, bucket_name: str, key: str, upload_id: str, part_number: int) -> Response:
        """
        Upload a part of a multipart upload.

        S3 Operation: PUT /{bucket}/{key}?partNumber=N&uploadId=X
        """
        try:
            if not upload_id or part_number < 1 or part_number > 10000:
                return error_response(
                    code='InvalidArgument',
                    message='Invalid uploadId or partNumber',
                    status_code=400
                )

            # Get upload metadata
            upload_data = self._get_upload_data(upload_id)
            if not upload_data:
                return error_response(
                    code='NoSuchUpload',
                    message='The specified multipart upload does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Verify bucket and key match
            if upload_data['bucket'] != bucket_name or upload_data['key'] != key:
                return error_response(
                    code='InvalidArgument',
                    message='Bucket or key does not match upload',
                    status_code=400
                )

            # Get part data
            part_data = request.get_data()
            etag = self._calculate_etag(part_data)

            # Store part data
            redis_client = self._get_redis()
            if redis_client:
                redis_client.setex(
                    self._get_part_key(upload_id, part_number),
                    MULTIPART_EXPIRE_SECONDS,
                    part_data
                )
            else:
                if not hasattr(context, '_multipart_parts'):
                    context._multipart_parts = {}
                context._multipart_parts[f"{upload_id}:{part_number}"] = part_data

            # Update upload metadata with part info
            upload_data['parts'][str(part_number)] = {
                'etag': etag,
                'size': len(part_data),
                'last_modified': datetime.utcnow().isoformat()
            }
            self._save_upload_data(upload_id, upload_data)

            return upload_part_response(etag=etag)

        except ValueError:
            return error_response(
                code='InvalidArgument',
                message='Invalid partNumber',
                status_code=400
            )
        except Exception as e:
            log.error("UploadPart failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                status_code=500
            )

    def complete_multipart_upload(self, bucket_name: str, key: str, upload_id: str) -> Response:
        """
        Complete a multipart upload by combining parts.

        S3 Operation: POST /{bucket}/{key}?uploadId=X

        Request body contains XML with list of parts and ETags.
        """
        try:
            if not upload_id:
                return error_response(
                    code='InvalidArgument',
                    message='Missing uploadId',
                    status_code=400
                )

            # Get upload metadata
            upload_data = self._get_upload_data(upload_id)
            if not upload_data:
                return error_response(
                    code='NoSuchUpload',
                    message='The specified multipart upload does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Verify bucket and key match
            if upload_data['bucket'] != bucket_name or upload_data['key'] != key:
                return error_response(
                    code='InvalidArgument',
                    message='Bucket or key does not match upload',
                    status_code=400
                )

            # Parse request body for part list
            body = request.get_data()
            try:
                root = _safe_fromstring(body)
                # Handle namespace
                ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
                parts = []
                for part in root.findall('.//Part', ns) or root.findall('.//Part'):
                    part_num = part.find('PartNumber', ns)
                    if part_num is None:
                        part_num = part.find('PartNumber')
                    etag = part.find('ETag', ns)
                    if etag is None:
                        etag = part.find('ETag')
                    if part_num is not None and etag is not None:
                        parts.append({
                            'part_number': int(part_num.text),
                            'etag': etag.text.strip('"')
                        })
            except Exception as e:
                log.warning("Failed to parse CompleteMultipartUpload body: %s", e)
                # Try to use all stored parts
                parts = [
                    {'part_number': int(k), 'etag': v['etag'].strip('"')}
                    for k, v in upload_data['parts'].items()
                ]

            # Sort parts by part number
            parts.sort(key=lambda x: x['part_number'])

            # Combine parts
            combined_data = b''
            redis_client = self._get_redis()

            for part in parts:
                part_number = part['part_number']

                if redis_client:
                    part_data = redis_client.get(
                        self._get_part_key(upload_id, part_number)
                    )
                else:
                    part_data = getattr(context, '_multipart_parts', {}).get(
                        f"{upload_id}:{part_number}"
                    )

                if not part_data:
                    return error_response(
                        code='InvalidPart',
                        message=f'Part {part_number} not found',
                        status_code=400
                    )

                combined_data += part_data

            # Upload combined object
            self.mc.upload_file(bucket_name, combined_data, key)

            # Calculate final ETag (for multipart: hash of hashes + part count)
            final_etag = f'"{hashlib.md5(combined_data).hexdigest()}-{len(parts)}"'

            # Clean up multipart data
            self._delete_upload_data(upload_id, len(parts))

            # Build location URL
            location = f"/{bucket_name}/{key}"

            return complete_multipart_upload_response(
                bucket=bucket_name,
                key=key,
                location=location,
                etag=final_etag
            )

        except Exception as e:
            log.error("CompleteMultipartUpload failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                status_code=500
            )

    def abort_multipart_upload(self, bucket_name: str, key: str, upload_id: str) -> Response:
        """
        Abort a multipart upload and clean up parts.

        S3 Operation: DELETE /{bucket}/{key}?uploadId=X
        """
        try:
            if not upload_id:
                return error_response(
                    code='InvalidArgument',
                    message='Missing uploadId',
                    status_code=400
                )

            # Get upload metadata
            upload_data = self._get_upload_data(upload_id)
            if not upload_data:
                return error_response(
                    code='NoSuchUpload',
                    message='The specified multipart upload does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Count parts for cleanup
            part_count = len(upload_data.get('parts', {}))

            # Clean up
            self._delete_upload_data(upload_id, part_count)

            return delete_response()

        except Exception as e:
            log.error("AbortMultipartUpload failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                status_code=500
            )

    def list_parts(self, bucket_name: str, key: str, upload_id: str) -> Response:
        """
        List parts that have been uploaded for a multipart upload.

        S3 Operation: GET /{bucket}/{key}?uploadId=X
        """
        try:
            if not upload_id:
                return error_response(
                    code='InvalidArgument',
                    message='Missing uploadId',
                    status_code=400
                )

            # Get upload metadata
            upload_data = self._get_upload_data(upload_id)
            if not upload_data:
                return error_response(
                    code='NoSuchUpload',
                    message='The specified multipart upload does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Build parts list
            parts = []
            for part_num_str, part_info in upload_data.get('parts', {}).items():
                parts.append({
                    'part_number': int(part_num_str),
                    'etag': part_info['etag'],
                    'size': part_info['size'],
                    'last_modified': part_info.get('last_modified', datetime.utcnow().isoformat())
                })

            # Sort by part number
            parts.sort(key=lambda x: x['part_number'])

            return list_parts_response(
                bucket=bucket_name,
                key=key,
                upload_id=upload_id,
                parts=parts
            )

        except Exception as e:
            log.error("ListParts failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                status_code=500
            )
