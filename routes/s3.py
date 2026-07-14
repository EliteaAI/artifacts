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

""" S3-Compatible API Routes """

import flask

from pylon.core.tools import log
from pylon.core.tools import web

from tools import MinioClient

from ..s3.auth import verify_s3_auth
from ..s3 import responses
from ..s3.utils import parse_bucket_and_key
from ..s3.handlers.bucket import BucketHandler
from ..s3.handlers.object import ObjectHandler
from ..s3.handlers.multipart import MultipartHandler


def _check_bucket_perm(credential: dict, bucket: str, required: str) -> bool:
    """Return True if the credential has the required permission for the bucket.

    Empty bucket_permissions = no restrictions (unrestricted access).
    required: 'read' or 'write'.
    'read' is satisfied by any non-empty permission list for the bucket.
    'write' requires 'write' explicitly present.
    """
    perms = credential.get('bucket_permissions', {})
    if not perms:
        return True
    allowed = perms.get(bucket, [])
    if not allowed:
        return False
    if required == 'read':
        return True
    return 'write' in allowed


class Route:  # pylint: disable=E1101,R0903
    """ S3-Compatible API Routes """

    @web.route(
        "/s3/",
        methods=["GET"],
        endpoint="s3_list_buckets",
    )
    def s3_list_buckets(self):
        """List all buckets (GET /)"""
        auth_result = verify_s3_auth(flask.request)
        if auth_result.get('error'):
            return responses.error_response('AccessDenied', auth_result['error'], status_code=403)

        credential = auth_result['credential']
        project_id = credential['project_id']

        try:
            project = self.context.rpc_manager.call.project_get_or_404(project_id=project_id)
            handler = BucketHandler(
                project,
                owner_id=credential['user_id'],
                owner_name=credential.get('name', ''),
                bucket_permissions=credential.get('bucket_permissions', {})
            )
            return handler.list_buckets()
        except Exception as e:
            log.exception("S3 ListBuckets error")
            return responses.error_response('InternalError', str(e), status_code=500)

    @web.route(
        "/s3/<string:bucket>",
        methods=["GET", "PUT", "DELETE", "HEAD"],
        endpoint="s3_bucket_operations",
        strict_slashes=False,
    )
    def s3_bucket_operations(self, bucket: str):
        """Bucket operations (GET/PUT/DELETE/HEAD /{bucket})"""
        auth_result = verify_s3_auth(flask.request)
        if auth_result.get('error'):
            return responses.error_response('AccessDenied', auth_result['error'], status_code=403)

        credential = auth_result['credential']
        project_id = credential['project_id']

        method = flask.request.method
        required_perm = 'write' if method in ('PUT', 'DELETE') else 'read'
        if not _check_bucket_perm(credential, bucket, required_perm):
            return responses.error_response('AccessDenied', 'Access denied to this bucket', status_code=403)

        try:
            project = self.context.rpc_manager.call.project_get_or_404(project_id=project_id)
            handler = BucketHandler(project)

            method = flask.request.method

            # Check for ListObjectsV2
            if method == 'GET' and flask.request.args.get('list-type') == '2':
                obj_handler = ObjectHandler(project)
                return obj_handler.list_objects_v2(bucket)

            # Check for ListObjects (v1)
            if method == 'GET' and 'list-type' not in flask.request.args:
                obj_handler = ObjectHandler(project)
                return obj_handler.list_objects_v2(bucket)

            if method == 'PUT':
                return handler.create_bucket(bucket)
            elif method == 'DELETE':
                return handler.delete_bucket(bucket)
            elif method == 'HEAD':
                return handler.head_bucket(bucket)
            else:
                # GET without list-type - list objects
                obj_handler = ObjectHandler(project)
                return obj_handler.list_objects_v2(bucket)

        except Exception as e:
            log.exception("S3 bucket operation error")
            return responses.error_response('InternalError', str(e), status_code=500)

    @web.route(
        "/s3/move_objects/<string:source_bucket>/<string:source_filename>/<string:destination_bucket>/<string:destination_filename>",
        methods=["POST"],
        endpoint="s3_move_objects",
        strict_slashes=False,
    )
    def s3_move_objects(
        self, source_bucket: str, source_filename: str, destination_bucket: str, destination_filename: str
    ):
        """Move objects from source bucket to destination bucket (GET /move_objects/{source_bucket}/{destination_bucket})"""
        auth_result = verify_s3_auth(flask.request)
        if auth_result.get('error'):
            return responses.error_response('AccessDenied', auth_result['error'], status_code=403)

        credential = auth_result['credential']
        project_id = credential['project_id']

        if not _check_bucket_perm(credential, source_bucket, 'read'):
            return responses.error_response('AccessDenied', 'Access denied to source bucket', status_code=403)
        if not _check_bucket_perm(credential, destination_bucket, 'write'):
            return responses.error_response('AccessDenied', 'Access denied to destination bucket', status_code=403)

        try:
            project = self.context.rpc_manager.call.project_get_or_404(project_id=project_id)
            handler = BucketHandler(project)
            return handler.move_object(source_bucket, source_filename, destination_bucket, destination_filename)
        except Exception as e:
            log.exception("S3 move objects error")
            return responses.error_response('InternalError', str(e), status_code=500)

    @web.route(
        "/s3/<string:bucket>/<path:key>",
        methods=["GET", "PUT", "DELETE", "HEAD", "POST"],
        endpoint="s3_object_operations",
        strict_slashes=False,
    )
    def s3_object_operations(self, bucket: str, key: str):
        """Object operations (GET/PUT/DELETE/HEAD/POST /{bucket}/{key})"""
        auth_result = verify_s3_auth(flask.request)
        if auth_result.get('error'):
            return responses.error_response('AccessDenied', auth_result['error'], status_code=403)

        credential = auth_result['credential']
        project_id = credential['project_id']

        obj_required = 'write' if flask.request.method in ('PUT', 'DELETE', 'POST') else 'read'
        if not _check_bucket_perm(credential, bucket, obj_required):
            return responses.error_response('AccessDenied', 'Access denied to this bucket', status_code=403)

        try:
            project = self.context.rpc_manager.call.project_get_or_404(project_id=project_id)
            obj_handler = ObjectHandler(project)
            mp_handler = MultipartHandler(
                project,
                project_id=credential['project_id'],
                user_id=credential['user_id']
            )

            method = flask.request.method
            args = flask.request.args

            # Multipart upload operations
            if 'uploads' in args:
                # POST /{bucket}/{key}?uploads - CreateMultipartUpload
                if method == 'POST':
                    return mp_handler.create_multipart_upload(bucket, key)

            if 'uploadId' in args:
                upload_id = args.get('uploadId')
                part_number = args.get('partNumber')

                if method == 'PUT' and part_number:
                    # PUT /{bucket}/{key}?partNumber=N&uploadId=X - UploadPart
                    return mp_handler.upload_part(bucket, key, upload_id, int(part_number))
                elif method == 'POST':
                    # POST /{bucket}/{key}?uploadId=X - CompleteMultipartUpload
                    return mp_handler.complete_multipart_upload(bucket, key, upload_id)
                elif method == 'DELETE':
                    # DELETE /{bucket}/{key}?uploadId=X - AbortMultipartUpload
                    return mp_handler.abort_multipart_upload(bucket, key, upload_id)
                elif method == 'GET':
                    # GET /{bucket}/{key}?uploadId=X - ListParts
                    return mp_handler.list_parts(bucket, key, upload_id)

            # Standard object operations
            if method == 'GET':
                return obj_handler.get_object(bucket, key)
            elif method == 'PUT':
                # Check for copy operation
                copy_source = flask.request.headers.get('x-amz-copy-source')
                if copy_source:
                    return obj_handler.copy_object(bucket, key, copy_source)
                return obj_handler.put_object(bucket, key)
            elif method == 'DELETE':
                return obj_handler.delete_object(bucket, key)
            elif method == 'HEAD':
                return obj_handler.head_object(bucket, key)

            return responses.error_response('MethodNotAllowed', 'Method not allowed', status_code=405)

        except Exception as e:
            log.exception("S3 object operation error")
            return responses.error_response('InternalError', str(e), status_code=500)
