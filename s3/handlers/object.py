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

""" S3 Object Operations Handler """

import hashlib
import mimetypes
from datetime import datetime
from flask import request, Response

from pylon.core.tools import log
from tools import MinioClient

from ..responses import (
    list_objects_v2_response,
    put_object_response,
    get_object_response,
    delete_response,
    head_response,
    copy_object_response,
    error_response
)


class ObjectHandler:
    """Handler for S3 object operations"""

    def __init__(self, project):
        """
        Initialize the object handler with project context.

        Args:
            project: The project object for MinioClient
        """
        self.project = project
        self.mc = MinioClient(project)

    @staticmethod
    def _calculate_etag(data: bytes) -> str:
        """Calculate ETag (MD5 hash) for object"""
        return f'"{hashlib.md5(data).hexdigest()}"'

    @staticmethod
    def _get_content_type(key: str) -> str:
        """Guess content type from key/filename"""
        content_type, _ = mimetypes.guess_type(key)
        return content_type or 'application/octet-stream'

    def list_objects_v2(self, bucket_name: str) -> Response:
        """
        List objects in a bucket.

        S3 Operation: GET /{bucket}?list-type=2

        Query parameters:
        - prefix: Limits results to keys beginning with prefix
        - delimiter: Character for grouping keys (usually '/')
        - max-keys: Maximum number of keys to return (default 1000)
        - continuation-token: Token for pagination
        - start-after: Start listing after this key
        """
        try:
            # Check if bucket exists
            existing_buckets = self.mc.list_bucket()
            if bucket_name not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Bucket {bucket_name} does not exist',
                    resource=f'/{bucket_name}',
                    status_code=404
                )

            # Get query parameters
            prefix = request.args.get('prefix', '')
            delimiter = request.args.get('delimiter', '')
            max_keys = int(request.args.get('max-keys', 1000))
            continuation_token = request.args.get('continuation-token', '')
            start_after = request.args.get('start-after', '')

            # List all files
            all_files = self.mc.list_files(bucket_name)

            # Filter by prefix
            if prefix:
                all_files = [f for f in all_files if f['name'].startswith(prefix)]

            # Filter by start-after
            if start_after:
                all_files = [f for f in all_files if f['name'] > start_after]

            # Handle continuation token (simple implementation - token is the last key)
            if continuation_token:
                all_files = [f for f in all_files if f['name'] > continuation_token]

            # Sort by key name
            all_files.sort(key=lambda x: x['name'])

            # Handle delimiter (group common prefixes)
            common_prefixes = []
            filtered_files = []

            if delimiter:
                seen_prefixes = set()
                for f in all_files:
                    key = f['name']
                    # Remove prefix from consideration
                    suffix = key[len(prefix):] if prefix else key

                    if delimiter in suffix:
                        # This key has the delimiter - extract common prefix
                        common_prefix = prefix + suffix.split(delimiter)[0] + delimiter
                        if common_prefix not in seen_prefixes:
                            seen_prefixes.add(common_prefix)
                            common_prefixes.append(common_prefix)
                    else:
                        filtered_files.append(f)
            else:
                filtered_files = all_files

            # Apply max-keys limit
            is_truncated = len(filtered_files) > max_keys
            filtered_files = filtered_files[:max_keys]

            # Set next continuation token if truncated
            next_token = ''
            if is_truncated and filtered_files:
                next_token = filtered_files[-1]['name']

            return list_objects_v2_response(
                bucket=bucket_name,
                objects=filtered_files,
                prefix=prefix,
                delimiter=delimiter,
                max_keys=max_keys,
                continuation_token=continuation_token,
                next_continuation_token=next_token,
                is_truncated=is_truncated,
                common_prefixes=common_prefixes
            )

        except Exception as e:
            log.error("ListObjectsV2 failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}',
                status_code=500
            )

    def put_object(self, bucket_name: str, key: str) -> Response:
        """
        Upload an object to a bucket.

        S3 Operation: PUT /{bucket}/{key}
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

            # Get request body
            data = request.get_data()

            # Upload the object
            self.mc.upload_file(bucket_name, data, key)

            # Calculate ETag
            etag = self._calculate_etag(data)

            return put_object_response(etag=etag)

        except Exception as e:
            log.error("PutObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )

    def get_object(self, bucket_name: str, key: str) -> Response:
        """
        Download an object from a bucket.

        S3 Operation: GET /{bucket}/{key}
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

            # Try to download the file
            try:
                data = self.mc.download_file(bucket_name, key)
            except Exception:
                return error_response(
                    code='NoSuchKey',
                    message='The specified key does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Calculate ETag
            etag = self._calculate_etag(data)

            # Get content type
            content_type = self._get_content_type(key)

            return get_object_response(
                body=data,
                content_type=content_type,
                etag=etag,
                last_modified=datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
            )

        except Exception as e:
            log.error("GetObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )

    def delete_object(self, bucket_name: str, key: str) -> Response:
        """
        Delete an object from a bucket.

        S3 Operation: DELETE /{bucket}/{key}
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

            # Try to delete the file (S3 returns 204 even if key doesn't exist)
            try:
                self.mc.remove_file(bucket_name, key)
            except Exception:
                pass  # S3 behavior: return success even if key doesn't exist

            return delete_response()

        except Exception as e:
            log.error("DeleteObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )

    def head_object(self, bucket_name: str, key: str) -> Response:
        """
        Get object metadata without downloading the body.

        S3 Operation: HEAD /{bucket}/{key}
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

            # Check if object exists and get size
            file_size = self.mc.get_file_size(bucket_name, key)
            if file_size == 0:
                # Could be empty file or non-existent - check file list
                files = self.mc.list_files(bucket_name)
                file_exists = any(f['name'] == key for f in files)
                if not file_exists:
                    return error_response(
                        code='NoSuchKey',
                        message='The specified key does not exist',
                        resource=f'/{bucket_name}/{key}',
                        status_code=404
                    )

            # Get content type
            content_type = self._get_content_type(key)

            # For proper ETag, we'd need to read the file (expensive)
            # Use placeholder based on size and key
            etag = f'"{hashlib.md5((key + str(file_size)).encode()).hexdigest()}"'

            return head_response(
                content_length=file_size,
                content_type=content_type,
                etag=etag,
                last_modified=datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
            )

        except Exception as e:
            log.error("HeadObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )

    def copy_object(self, bucket_name: str, key: str, copy_source: str) -> Response:
        """
        Copy an object.

        S3 Operation: PUT /{bucket}/{key} with x-amz-copy-source header

        Args:
            bucket_name: Destination bucket
            key: Destination key
            copy_source: Source path (bucket/key)
        """
        try:
            if not copy_source:
                return error_response(
                    code='InvalidRequest',
                    message='x-amz-copy-source header required',
                    status_code=400
                )

            # Parse source bucket and key
            # Format: /bucket/key or bucket/key
            copy_source = copy_source.lstrip('/')
            parts = copy_source.split('/', 1)
            if len(parts) != 2:
                return error_response(
                    code='InvalidRequest',
                    message='Invalid x-amz-copy-source format',
                    status_code=400
                )

            source_bucket, source_key = parts

            # Check source bucket exists
            existing_buckets = self.mc.list_bucket()
            if source_bucket not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Source bucket {source_bucket} does not exist',
                    resource=f'/{source_bucket}/{source_key}',
                    status_code=404
                )

            # Download source object
            try:
                data = self.mc.download_file(source_bucket, source_key)
            except Exception:
                return error_response(
                    code='NoSuchKey',
                    message='Source key does not exist',
                    resource=f'/{source_bucket}/{source_key}',
                    status_code=404
                )

            # Check destination bucket exists
            if bucket_name not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Destination bucket {bucket_name} does not exist',
                    resource=f'/{bucket_name}/{key}',
                    status_code=404
                )

            # Upload to destination
            self.mc.upload_file(bucket_name, data, key)

            # Return copy response
            etag = self._calculate_etag(data)
            return copy_object_response(etag=etag, last_modified=datetime.utcnow())

        except Exception as e:
            log.error("CopyObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}/{key}',
                status_code=500
            )
