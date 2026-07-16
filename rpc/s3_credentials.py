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

""" S3 API Credentials RPC Methods - Uses Configurations System """

from datetime import datetime
from typing import Optional, List, Dict

from pylon.core.tools import web, log

from tools import context

from ..models.pd.s3_credentials import (
    generate_access_key_id,
    generate_secret_access_key
)


class RPC:
    """S3 API Credentials RPC methods using configurations system"""

    @web.rpc('s3_credentials_create', 'create')
    def create(self, name: str, project_id: int, user_id: int,
               expires_at: Optional[datetime] = None,
               permissions: Optional[List[str]] = None,
               bucket_permissions: Optional[Dict] = None,
               allow_multiple: bool = False) -> Optional[Dict]:
        """
        Create new S3 API credentials as a configuration item.

        Creates a configuration of type 's3_api_credentials' that will be
        visible in the Configurations UI.

        Args:
            allow_multiple: If False (default), returns existing active credential
                           for this user instead of creating a duplicate.

        Returns the full credential including secret (only time secret is returned).
        """
        rpc = context.rpc_manager

        # Check for existing active credential for this user (unless explicitly allowed)
        if not allow_multiple:
            existing = self.list_by_project(project_id)
            for cred in existing:
                if cred.get('user_id') == user_id and cred.get('is_active', True):
                    log.info("Returning existing S3 credential for user %d in project %d", user_id, project_id)
                    full_cred = self.get_by_access_key(cred['access_key_id'])
                    if full_cred:
                        return full_cred

        # Generate access key and secret
        access_key_id = generate_access_key_id(project_id)
        secret_access_key = generate_secret_access_key()

        # Create configuration payload
        config_payload = {
            'project_id': project_id,
            'type': 's3_api_credentials',
            'elitea_title': access_key_id,  # Use access_key as unique identifier
            'label': name,
            'shared': False,  # S3 credentials are project-specific
            'author_id': user_id,
            'data': {
                'access_key_id': access_key_id,
                'secret_access_key': secret_access_key,
                'user_id': user_id,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'permissions': permissions or [],
                'bucket_permissions': bucket_permissions or {},
                'is_active': True,
                'created_at': datetime.utcnow().isoformat()
            }
        }

        try:
            # Use configurations RPC to create
            config, was_created = rpc.timeout(5).configurations_create_if_not_exists(config_payload)

            if not was_created:
                log.warning("S3 credential with access_key %s already exists", access_key_id)
                return None

            log.info("Created S3 API credential %s for project %d", access_key_id, project_id)

            # Return with secret included (only time it's returned)
            return {
                'id': config.get('id'),
                'access_key_id': access_key_id,
                'secret_access_key': secret_access_key,
                'name': name,
                'project_id': project_id,
                'user_id': user_id,
                'created_at': config_payload['data']['created_at'],
                'expires_at': config_payload['data']['expires_at'],
                'permissions': permissions or [],
                'bucket_permissions': bucket_permissions or {},
                'is_active': True
            }

        except Exception as e:
            log.error("Failed to create S3 credential: %s", e)
            return None

    @web.rpc('s3_credentials_get_by_access_key', 'get_by_access_key')
    def get_by_access_key(self, access_key_id: str) -> Optional[Dict]:
        """
        Get S3 credentials by access key ID.

        Looks up the configuration by elitea_title (which stores the access_key_id).
        Used by S3 API authentication to validate requests.
        """
        rpc = context.rpc_manager

        try:
            # Extract project_id from access_key (ELITEA + 6 digit project_id + random)
            # Case-insensitive check for the prefix
            if not access_key_id.upper().startswith('ELITEA') or len(access_key_id) != 20:
                log.warning("Invalid access key format: %s", access_key_id)
                return None

            project_id_str = access_key_id[6:12]  # Extract 6 digit project ID
            try:
                project_id = int(project_id_str)
            except ValueError:
                log.warning("Could not extract project_id from access_key: %s", access_key_id)
                return None

            # Look up configuration by elitea_title (stored lowercase)
            configs = rpc.timeout(5).configurations_get_filtered_project(
                project_id=project_id,
                include_shared=False,
                filter_fields={
                    'type': 's3_api_credentials',
                    'elitea_title': access_key_id.lower()
                }
            )

            if not configs:
                log.debug("No S3 credential found for access_key: %s", access_key_id)
                return None

            config = configs[0]
            data = config.get('data', {})

            # Check if active
            if not data.get('is_active', True):
                log.debug("S3 credential %s is inactive", access_key_id)
                return None

            # Check expiration
            expires_at = data.get('expires_at')
            if expires_at:
                try:
                    expires_dt = datetime.fromisoformat(expires_at)
                    if datetime.utcnow() > expires_dt:
                        log.debug("S3 credential %s has expired", access_key_id)
                        return None
                except:
                    pass

            # Return credential data
            return {
                'id': config.get('id'),
                'access_key_id': data.get('access_key_id'),
                'secret_access_key': data.get('secret_access_key'),
                'name': config.get('label', ''),
                'project_id': project_id,
                'user_id': data.get('user_id'),
                'created_at': data.get('created_at'),
                'expires_at': data.get('expires_at'),
                'permissions': data.get('permissions', []),
                'bucket_permissions': data.get('bucket_permissions', {}),
                'is_active': data.get('is_active', True)
            }

        except Exception as e:
            log.warning("Failed to get S3 credential %s: %s", access_key_id, e)
            return None

    @web.rpc('s3_credentials_list_by_project', 'list_by_project')
    def list_by_project(self, project_id: int) -> List[Dict]:
        """
        List all S3 API credentials for a project.

        Returns credentials without secret keys (secrets are only shown on creation).
        """
        rpc = context.rpc_manager

        try:
            configs = rpc.timeout(5).configurations_get_filtered_project(
                project_id=project_id,
                include_shared=False,
                filter_fields={'type': 's3_api_credentials'}
            )

            credentials = []
            for config in configs:
                data = config.get('data', {})
                credentials.append({
                    'id': config.get('id'),
                    'access_key_id': data.get('access_key_id'),
                    'name': config.get('label', ''),
                    'project_id': project_id,
                    'user_id': data.get('user_id'),
                    'created_at': data.get('created_at'),
                    'expires_at': data.get('expires_at'),
                    'permissions': data.get('permissions', []),
                    'bucket_permissions': data.get('bucket_permissions', {}),
                    'is_active': data.get('is_active', True)
                    # Note: secret_access_key is NOT included
                })

            return credentials

        except Exception as e:
            log.warning("Failed to list S3 credentials for project %d: %s", project_id, e)
            return []

    @web.rpc('s3_credentials_delete', 'delete')
    def delete(self, access_key_id: str, project_id: int) -> bool:
        """
        Delete (deactivate) S3 credentials.

        Marks the credential as inactive rather than deleting for audit purposes.
        """
        rpc = context.rpc_manager

        try:
            # Look up the configuration
            configs = rpc.timeout(5).configurations_get_filtered_project(
                project_id=project_id,
                include_shared=False,
                filter_fields={
                    'type': 's3_api_credentials',
                    'elitea_title': access_key_id
                }
            )

            if not configs:
                log.warning("S3 credential not found: %s", access_key_id)
                return False

            config = configs[0]
            config_id = config.get('id')
            data = config.get('data', {})

            # Mark as inactive
            data['is_active'] = False
            data['deleted_at'] = datetime.utcnow().isoformat()

            # Update the configuration
            rpc.timeout(5).configurations_update(
                project_id=project_id,
                config_id=config_id,
                payload={'data': data}
            )

            log.info("Deleted (deactivated) S3 credential %s", access_key_id)
            return True

        except Exception as e:
            log.error("Failed to delete S3 credential %s: %s", access_key_id, e)
            return False

    @web.rpc('s3_credentials_get_or_create_for_bearer', 'get_or_create_for_bearer')
    def get_or_create_for_bearer(self, project_id: int, user_id: int,
                                  user_name: str = 'Bearer User') -> Optional[Dict]:
        """
        Get existing S3 credentials for a project or create new ones.

        Used for Bearer token authentication where we need to map
        a user's Bearer token to S3 credentials for a specific project.

        Args:
            project_id: The project ID to get/create credentials for
            user_id: The user ID from the Bearer token
            user_name: Display name for the credential

        Returns:
            Credential dict (without secret for existing, with secret for new)
        """
        try:
            credentials = self.list_by_project(project_id)

            # Only return credentials belonging to this user
            for cred in credentials:
                if cred.get('user_id') == user_id and cred.get('is_active', True):
                    full_cred = self.get_by_access_key(cred['access_key_id'])
                    if full_cred:
                        return full_cred

            # No credential found for this user - create new one
            new_cred = self.create(
                name=f'Bearer - {user_name}',
                project_id=project_id,
                user_id=user_id,
                expires_at=None,
                permissions=['read', 'write']
            )

            return new_cred

        except Exception as e:
            log.error("Failed to get/create S3 credentials for bearer: %s", e)
            return None

    @web.rpc('s3_credentials_update_bucket_permissions', 'update_bucket_permissions')
    def update_bucket_permissions(self, access_key_id: str, project_id: int,
                                   bucket_permissions: Dict) -> Optional[Dict]:
        """
        Update bucket_permissions on an existing S3 credential.

        bucket_permissions: {bucket_name: ['read', 'write']} or {} (unrestricted).
        Pass an empty dict to remove all bucket restrictions.
        """
        rpc = context.rpc_manager

        try:
            configs = rpc.timeout(5).configurations_get_filtered_project(
                project_id=project_id,
                include_shared=False,
                filter_fields={
                    'type': 's3_api_credentials',
                    'elitea_title': access_key_id.lower()
                }
            )

            if not configs:
                log.warning("S3 credential not found: %s", access_key_id)
                return None

            config = configs[0]
            config_id = config.get('id')
            data = config.get('data', {})

            data['bucket_permissions'] = bucket_permissions

            rpc.timeout(5).configurations_update(
                project_id=project_id,
                config_id=config_id,
                payload={'data': data}
            )

            log.info("Updated bucket_permissions for S3 credential %s", access_key_id)

            return {
                'id': config_id,
                'access_key_id': access_key_id,
                'project_id': project_id,
                'user_id': data.get('user_id'),
                'permissions': data.get('permissions', []),
                'bucket_permissions': bucket_permissions,
                'is_active': data.get('is_active', True)
            }

        except Exception as e:
            log.error("Failed to update bucket_permissions for %s: %s", access_key_id, e)
            return None

    @web.rpc('s3_credentials_rotate', 'rotate')
    def rotate(self, access_key_id: str, project_id: int) -> Optional[Dict]:
        """
        Rotate S3 credentials (generate new secret).

        Returns the credential with new secret (only time new secret is returned).
        """
        rpc = context.rpc_manager

        try:
            # Look up the configuration
            configs = rpc.timeout(5).configurations_get_filtered_project(
                project_id=project_id,
                include_shared=False,
                filter_fields={
                    'type': 's3_api_credentials',
                    'elitea_title': access_key_id
                }
            )

            if not configs:
                log.warning("S3 credential not found for rotation: %s", access_key_id)
                return None

            config = configs[0]
            config_id = config.get('id')
            data = config.get('data', {})

            # Generate new secret
            new_secret = generate_secret_access_key()
            data['secret_access_key'] = new_secret
            data['rotated_at'] = datetime.utcnow().isoformat()

            # Update the configuration
            rpc.timeout(5).configurations_update(
                project_id=project_id,
                config_id=config_id,
                payload={'data': data}
            )

            log.info("Rotated S3 credential %s", access_key_id)

            # Return with new secret
            return {
                'id': config_id,
                'access_key_id': access_key_id,
                'secret_access_key': new_secret,
                'name': config.get('label', ''),
                'project_id': project_id,
                'user_id': data.get('user_id'),
                'created_at': data.get('created_at'),
                'expires_at': data.get('expires_at'),
                'rotated_at': data['rotated_at'],
                'permissions': data.get('permissions', []),
                'bucket_permissions': data.get('bucket_permissions', {}),
                'is_active': data.get('is_active', True)
            }

        except Exception as e:
            log.error("Failed to rotate S3 credential %s: %s", access_key_id, e)
            return None
