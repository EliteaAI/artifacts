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

""" S3 Credentials REST API """

from datetime import datetime
from flask import request

from pylon.core.tools import log
from tools import api_tools, auth, register_openapi

from ...models.pd.api_models import S3CredentialCreateRequest

_PROJECT_PARAM = {"name": "project_id", "in": "path", "schema": {"type": "string"},
                  "description": "Project identifier."}
_ACCESS_KEY_PARAM = {"name": "access_key_id", "in": "path", "schema": {"type": "string"},
                     "description": "S3 access key ID."}


class ProjectAPI(api_tools.APIModeHandler):
    """S3 Credentials API for project scope"""

    @register_openapi(
        name="List or Get S3 Credentials",
        description="List all S3 API credentials for a project, or get a specific credential by access key ID.",
        parameters=[
            _PROJECT_PARAM,
            {"name": "access_key_id", "in": "path", "schema": {"type": "string"},
             "description": "Access key ID (optional — omit to list all credentials)."},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.view"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": True, "editor": True},
            "default": {"admin": True, "viewer": True, "editor": True},
            "developer": {"admin": True, "viewer": True, "editor": True},
        }
    })
    def get(self, project_id: int, access_key_id: str = None):
        """
        List S3 credentials for a project, or get a specific credential.

        GET /api/v1/artifacts/s3_credentials/{project_id}
        GET /api/v1/artifacts/s3_credentials/{project_id}/{access_key_id}
        """
        rpc = self.module.context.rpc_manager

        if access_key_id:
            # Get specific credential
            credential = rpc.call.s3_credentials_get_by_access_key(access_key_id=access_key_id)
            if not credential:
                return {'error': 'Credential not found'}, 404
            if credential.get('project_id') != project_id:
                return {'error': 'Credential not found'}, 404

            # Remove secret from response
            public_credential = {k: v for k, v in credential.items()
                                if k != 'secret_access_key'}
            return public_credential, 200

        # List all credentials for project
        credentials = rpc.call.s3_credentials_list_by_project(project_id=project_id)
        return {
            'total': len(credentials),
            'rows': credentials
        }, 200

    @register_openapi(
        name="Create S3 Credential",
        description="Create new S3 API credentials for a project. The secret_access_key is returned only in this response.",
        parameters=[_PROJECT_PARAM],
        request_body=S3CredentialCreateRequest,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.create"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
            "developer": {"admin": True, "viewer": False, "editor": True},
        }
    })
    def post(self, project_id: int):
        """
        Create new S3 credentials.

        POST /api/v1/artifacts/s3_credentials/{project_id}

        Request body:
        {
            "name": "My S3 Key",
            "expires_in_days": 365  // optional
        }

        Response includes secret_access_key (only time it's returned).
        """
        rpc = self.module.context.rpc_manager
        user = auth.current_user()

        if not user:
            return {'error': 'Unauthorized'}, 401

        args = request.json or {}
        name = args.get('name', 'S3 Access Key')

        # Calculate expiration if provided
        expires_at = None
        expires_in_days = args.get('expires_in_days')
        if expires_in_days:
            from datetime import timedelta
            expires_at = datetime.utcnow() + timedelta(days=int(expires_in_days))

        permissions = args.get('permissions', [])

        # Create the credential
        credential = rpc.call.s3_credentials_create(
            name=name,
            project_id=project_id,
            user_id=user['id'],
            expires_at=expires_at,
            permissions=permissions
        )

        if not credential:
            return {'error': 'Failed to create credential'}, 500

        log.info("Created S3 credential %s for project %d by user %d",
                 credential['access_key_id'], project_id, user['id'])

        return credential, 201

    @register_openapi(
        name="Delete S3 Credential",
        description="Delete an S3 credential by access key ID.",
        parameters=[_PROJECT_PARAM, _ACCESS_KEY_PARAM],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.delete"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
            "developer": {"admin": True, "viewer": False, "editor": True},
        }
    })
    def delete(self, project_id: int, access_key_id: str = None):
        """
        Delete S3 credentials.

        DELETE /api/v1/artifacts/s3_credentials/{project_id}/{access_key_id}
        """
        if not access_key_id:
            return {'error': 'access_key_id required'}, 400

        rpc = self.module.context.rpc_manager

        success = rpc.call.s3_credentials_delete(
            access_key_id=access_key_id,
            project_id=project_id
        )

        if not success:
            return {'error': 'Failed to delete credential'}, 404

        return {'message': 'Deleted'}, 200

    @register_openapi(
        name="Rotate S3 Credential",
        description="Rotate S3 credentials — generates a new secret_access_key. The new secret is returned only in this response.",
        parameters=[_PROJECT_PARAM, _ACCESS_KEY_PARAM],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.s3_credentials.edit"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
            "developer": {"admin": True, "viewer": False, "editor": True},
        }
    })
    def put(self, project_id: int, access_key_id: str = None):
        """
        Rotate S3 credentials (generate new secret).

        PUT /api/v1/artifacts/s3_credentials/{project_id}/{access_key_id}

        Response includes new secret_access_key.
        """
        if not access_key_id:
            return {'error': 'access_key_id required'}, 400

        rpc = self.module.context.rpc_manager

        credential = rpc.call.s3_credentials_rotate(
            access_key_id=access_key_id,
            project_id=project_id
        )

        if not credential:
            return {'error': 'Failed to rotate credential'}, 404

        log.info("Rotated S3 credential %s for project %d", access_key_id, project_id)

        return credential, 200


class API(api_tools.APIBase):
    url_params = [
        '<string:project_id>',
        '<string:mode>/<string:project_id>',
        '<string:project_id>/<string:access_key_id>',
        '<string:mode>/<string:project_id>/<string:access_key_id>',
    ]

    mode_handlers = {
        'default': ProjectAPI,
    }
