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

""" Bucket Permissions REST API — manage per-user bucket access """

from flask import request
from pylon.core.tools import log
from tools import api_tools, auth, register_openapi


class ProjectAPI(api_tools.APIModeHandler):

    @register_openapi(
        name="List Bucket Permissions",
        description="List all S3 credentials with their bucket_permissions for a project (admin only).",
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.view"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": False},
            "default": {"admin": True, "viewer": False, "editor": False},
        }
    })
    def get(self, project_id: int):
        rpc = self.module.context.rpc_manager
        credentials = rpc.call.s3_credentials_list_by_project(project_id=project_id)
        rows = [
            {
                'access_key_id': c['access_key_id'],
                'user_id': c['user_id'],
                'name': c['name'],
                'bucket_permissions': c.get('bucket_permissions', {}),
            }
            for c in credentials if c.get('is_active', True)
        ]
        return {'total': len(rows), 'rows': rows}, 200

    @register_openapi(
        name="Set Bucket Permissions",
        description=(
            "Set bucket_permissions for a specific S3 credential. "
            "Pass empty bucket_permissions ({}) to remove all restrictions."
        ),
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.edit"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
        }
    })
    def put(self, project_id: int):
        """
        Body: {
            "access_key_id": "ELITEA000001XXXXXXXX",
            "bucket_permissions": {"reports": ["read"], "datasets": ["read", "write"]}
        }
        """
        args = request.json or {}
        access_key_id = args.get('access_key_id')
        bucket_permissions = args.get('bucket_permissions')

        if not access_key_id:
            return {'error': 'access_key_id is required'}, 400
        if bucket_permissions is None:
            return {'error': 'bucket_permissions is required'}, 400
        if not isinstance(bucket_permissions, dict):
            return {'error': 'bucket_permissions must be a dict'}, 400

        # Validate permission values
        for bucket, perms in bucket_permissions.items():
            if not isinstance(perms, list):
                return {'error': f'Permissions for bucket {bucket!r} must be a list'}, 400
            invalid = set(perms) - {'read', 'write'}
            if invalid:
                return {'error': f'Invalid permissions {invalid} for bucket {bucket!r}. Allowed: read, write'}, 400

        rpc = self.module.context.rpc_manager
        result = rpc.call.s3_credentials_update_bucket_permissions(
            access_key_id=access_key_id,
            project_id=project_id,
            bucket_permissions=bucket_permissions
        )

        if not result:
            return {'error': 'Credential not found or update failed'}, 404

        return result, 200

    @register_openapi(
        name="Remove Bucket Permission",
        description="Remove a specific bucket from a credential's bucket_permissions.",
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.edit"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
        }
    })
    def delete(self, project_id: int):
        """
        Body: {
            "access_key_id": "ELITEA000001XXXXXXXX",
            "bucket": "reports"
        }
        Removes the bucket entry from bucket_permissions. Does not delete the credential.
        """
        args = request.json or {}
        access_key_id = args.get('access_key_id')
        bucket = args.get('bucket')

        if not access_key_id:
            return {'error': 'access_key_id is required'}, 400
        if not bucket:
            return {'error': 'bucket is required'}, 400

        rpc = self.module.context.rpc_manager
        credential = rpc.call.s3_credentials_get_by_access_key(access_key_id=access_key_id)
        if not credential or credential.get('project_id') != project_id:
            return {'error': 'Credential not found'}, 404

        bucket_permissions = credential.get('bucket_permissions', {})
        bucket_permissions.pop(bucket, None)

        result = rpc.call.s3_credentials_update_bucket_permissions(
            access_key_id=access_key_id,
            project_id=project_id,
            bucket_permissions=bucket_permissions
        )

        if not result:
            return {'error': 'Update failed'}, 500

        return result, 200


class API(api_tools.APIBase):
    url_params = [
        '<int:project_id>',
        '<string:mode>/<int:project_id>',
    ]

    mode_handlers = {
        'default': ProjectAPI,
    }
