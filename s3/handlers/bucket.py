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

""" S3 Bucket Operations Handler """

from datetime import datetime
from flask import Response

from pylon.core.tools import log
from tools import MinioClient

from ..responses import (
    list_buckets_response,
    create_bucket_response,
    delete_response,
    head_response,
    error_response
)


class BucketHandler:
    """Handler for S3 bucket operations"""

    def __init__(self, project, owner_id: int = None, owner_name: str = None,
                 bucket_permissions: dict = None):
        self.project = project
        self.owner_id = owner_id or 0
        self.owner_name = owner_name or ''
        self.bucket_permissions = bucket_permissions or {}
        self.mc = MinioClient(project)

    def list_buckets(self) -> Response:
        """
        List all buckets for the authenticated project.

        S3 Operation: GET /
        """
        try:
            buckets = self.mc.list_bucket()

            if self.bucket_permissions:
                buckets = [b for b in buckets if b in self.bucket_permissions]

            # Build bucket list with metadata
            bucket_list = []
            for bucket_name in buckets:
                bucket_info = {
                    'name': bucket_name,
                    'creation_date': datetime.utcnow()  # MinIO doesn't track creation date
                }

                # Get bucket size
                try:
                    bucket_size = self.mc.get_bucket_size(bucket_name)
                    bucket_info['size'] = bucket_size
                except Exception as size_err:
                    log.debug(f"Failed to get size for bucket {bucket_name}: {size_err}")
                    bucket_info['size'] = 0

                # Try to get lifecycle/retention info
                try:
                    lifecycle = self.mc.get_bucket_lifecycle(bucket_name)
                    rules = lifecycle.get('Rules', [])
                    if rules:
                        expiration = rules[0].get('Expiration', {})
                        retention_days = expiration.get('Days')
                        if retention_days:
                            bucket_info['retention_days'] = retention_days
                except Exception as lifecycle_err:
                    log.debug(f"No lifecycle policy for bucket {bucket_name}: {lifecycle_err}")
                    bucket_info['retention_days'] = None

                # Get is_pinned from bucket tags
                try:
                    tags_response = self.mc.get_bucket_tags(bucket_name)
                    tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])} if tags_response else {}
                    bucket_info['is_pinned'] = tags.get('is_pinned', 'false') == 'true'
                except Exception as tag_err:
                    log.debug(f"Failed to get tags for bucket {bucket_name}: {tag_err}")
                    bucket_info['is_pinned'] = False

                bucket_list.append(bucket_info)

            # Sort: pinned first, then alphabetically by name (case-insensitive)
            bucket_list.sort(key=lambda b: (not b.get('is_pinned', False), b['name'].lower()))

            return list_buckets_response(
                buckets=bucket_list,
                owner_id=str(self.owner_id),
                owner_display_name=self.owner_name
            )

        except Exception as e:
            log.exception("ListBuckets failed")
            return error_response(
                code='InternalError',
                message=str(e),
                status_code=500
            )

    def create_bucket(self, bucket_name: str) -> Response:
        """
        Create a new bucket.

        S3 Operation: PUT /{bucket}
        """
        try:
            # Check if bucket already exists
            existing_buckets = self.mc.list_bucket()
            if bucket_name in existing_buckets:
                return error_response(
                    code='BucketAlreadyExists',
                    message=f'Bucket {bucket_name} already exists',
                    resource=f'/{bucket_name}',
                    status_code=409
                )

            # Create the bucket
            result = self.mc.create_bucket(bucket=bucket_name, bucket_type='local')

            if isinstance(result, dict) and result.get('error'):
                return error_response(
                    code='InternalError',
                    message=result['error'],
                    resource=f'/{bucket_name}',
                    status_code=500
                )

            location = result.get('Location', f'/{self.mc.format_bucket_name(bucket_name)}')
            return create_bucket_response(location)

        except Exception as e:
            log.error("CreateBucket failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}',
                status_code=500
            )

    def delete_bucket(self, bucket_name: str) -> Response:
        """
        Delete a bucket.

        S3 Operation: DELETE /{bucket}

        Note: Bucket must be empty before deletion.
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

            # Check if bucket is empty
            files = self.mc.list_files(bucket_name)
            if files:
                return error_response(
                    code='BucketNotEmpty',
                    message='The bucket you tried to delete is not empty',
                    resource=f'/{bucket_name}',
                    status_code=409
                )

            # Delete the bucket
            self.mc.remove_bucket(bucket_name)
            return delete_response()

        except Exception as e:
            log.error("DeleteBucket failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}',
                status_code=500
            )

    def head_bucket(self, bucket_name: str) -> Response:
        """
        Check if a bucket exists.

        S3 Operation: HEAD /{bucket}

        Returns 200 if bucket exists, 404 if not.
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

            return head_response()

        except Exception as e:
            log.error("HeadBucket failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}',
                status_code=500
            )

    def update_bucket_tags(self, bucket_name: str, new_tags: dict) -> Response:
        """
        Update bucket tags (merge with existing).

        Used for updating is_pinned and other metadata.
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

            # Get existing tags and merge
            response = self.mc.get_bucket_tags(bucket_name)
            existing_tags = {
                tag['Key']: tag['Value']
                for tag in response.get('TagSet', [])
            } if response else {}
            existing_tags.update(new_tags)
            self.mc.set_bucket_tags(bucket=bucket_name, tags=existing_tags)

            return Response(
                '{"message": "Updated"}',
                status=200,
                mimetype='application/json'
            )

        except Exception as e:
            log.error("UpdateBucketTags failed: %s", e)
            return error_response(
                code='InternalError',
                message='Failed to update bucket tags',
                resource=f'/{bucket_name}',
                status_code=500
            )

    def get_bucket_location(self, bucket_name: str, region: str = 'us-east-1') -> Response:
        """
        Get bucket location (region).

        S3 Operation: GET /{bucket}?location
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

            # Return location constraint XML
            from xml.etree.ElementTree import Element, tostring
            root = Element('LocationConstraint', xmlns='http://s3.amazonaws.com/doc/2006-03-01/')
            root.text = region

            xml_str = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='utf-8')
            return Response(xml_str, status=200, mimetype='application/xml')

        except Exception as e:
            log.error("GetBucketLocation failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{bucket_name}',
                status_code=500
            )

    def move_object(self, source_bucket: str, source_key: str, dest_bucket: str, dest_key: str) -> Response:
        """
        Move an object from source bucket to destination bucket.

        Uses server-side copy for optimal performance (no data transfer through application).
        Limited to files up to 5GB.
        """
        try:
            # Check if source bucket exists
            existing_buckets = self.mc.list_bucket()
            if source_bucket not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Source bucket {source_bucket} does not exist',
                    resource=f'/{source_bucket}/{source_key}',
                    status_code=404
                )

            # Check if destination bucket exists
            if dest_bucket not in existing_buckets:
                return error_response(
                    code='NoSuchBucket',
                    message=f'Destination bucket {dest_bucket} does not exist',
                    resource=f'/{dest_bucket}/{dest_key}',
                    status_code=404
                )

            # Check if source object exists
            source_files = self.mc.list_files(source_bucket)
            source_exists = any(f['name'] == source_key for f in source_files)
            if not source_exists:
                return error_response(
                    code='NoSuchKey',
                    message='Source key does not exist',
                    resource=f'/{source_bucket}/{source_key}',
                    status_code=404
                )

            # Perform server-side move (copy + delete)
            self.mc.move_object(source_bucket, source_key, dest_bucket, dest_key)

            return Response('', status=200)

        except ValueError as e:
            # Handle size limit errors
            log.warning("MoveObject size limit exceeded: %s", e)
            return error_response(
                code='EntityTooLarge',
                message=str(e),
                resource=f'/{source_bucket}/{source_key}',
                status_code=400
            )
        except Exception as e:
            log.error("MoveObject failed: %s", e)
            return error_response(
                code='InternalError',
                message=str(e),
                resource=f'/{source_bucket}/{source_key}',
                status_code=500
            )
