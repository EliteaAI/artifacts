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

""" Module """
from queue import Empty

from pylon.core.tools import log  # pylint: disable=E0611,E0401
from pylon.core.tools import module  # pylint: disable=E0611,E0401
from pylon.core.tools import web  # pylint: disable=E0611,E0401
from tools import theme

from .models.pd.configuration import configuration_record
from .models.pd.s3_credentials import s3_api_credentials_configuration_record


class Module(module.ModuleModel):
    """ Task module """

    def __init__(self, context, descriptor):
        self.context = context
        self.descriptor = descriptor

    def init(self):
        """ Init module """
        log.info("Initializing module Artifacts")

        # Initialize all components using Elitea's auto-registration
        # This includes: api/, slots/, events/, rpc/, routes/, methods/, inits/
        self.descriptor.init_all()

        theme.register_subsection(
            "configuration", "artifacts",
            "Artifacts",
            title="Artifacts",
            kind="slot",
            permissions={
                "permissions": ["configuration.artifacts"],
                "recommended_roles": {
                    "administration": {"admin": True, "viewer": True, "editor": True},
                    "default": {"admin": True, "viewer": True, "editor": True},
                    "developer": {"admin": True, "viewer": True, "editor": True},
                }},
            prefix="artifacts_",
            weight=5,
        )

        theme.register_mode_subsection(
            "administration", "configuration",
            "artifacts", "Artifacts",
            title="Artifacts",
            kind="slot",
            permissions={
                "permissions": ["configuration.artifacts"],
                "recommended_roles": {
                    "administration": {"admin": True, "viewer": True, "editor": True},
                    "default": {"admin": True, "viewer": True, "editor": True},
                    "developer": {"admin": True, "viewer": True, "editor": True},
                }},
            prefix="administration_artifacts_",
            # icon_class="fas fa-server fa-fw",
            # weight=2,
        )

    def deinit(self):  # pylint: disable=R0201
        """ De-init module """
        log.info("De-initializing module Artifacts")
        # S3 public rule cleanup is handled in methods/s3.py via @web.deinit()

    def ready(self):
        log.info("Artifacts ready callback")
        from tools import config, this

        try:
            this.for_module("admin").module.register_admin_task(
                "migrate_artifact_buckets_retention", self.migrate_artifact_buckets_retention
            )
            this.for_module("admin").module.register_admin_task(
                "migration_rename_wiki_bucket", self.migration_rename_wiki_bucket
            )
        except Exception as e:
            log.exception("Failed to register admin tasks: %s", e)

        from .models.pd.configuration import S3Config
        try:
            # Register S3 storage configuration type
            self.context.rpc_manager.timeout(2).configurations_register(
               **configuration_record
            )

            # Register S3 API credentials configuration type
            self.context.rpc_manager.timeout(2).configurations_register(
               **s3_api_credentials_configuration_record
            )

            try:
                from tools import elitea_config  # pylint: disable=C0415,E0401
                public_project_id = int(elitea_config.get("ai_project_id", 1))
                try:
                    config, was_created = self.context.rpc_manager.timeout(2).configurations_create_if_not_exists(dict(
                        project_id=public_project_id,
                        type='s3',
                        elitea_title='elitea_s3_storage',
                        label='Elitea S3 storage',
                        shared=True,
                        data={
                            'access_key': config.MINIO_ACCESS_KEY,
                            'secret_access_key': config.MINIO_SECRET_KEY,
                            'region_name': config.MINIO_REGION,
                            'use_compatible_storage': True,
                            'storage_url': config.MINIO_URL
                        }
                    ))
                    if not was_created:
                        log.debug(f"'Configuration {config['type']}: {config['title']}' already exists")
                    log.info(f"Artifacts config created {config=}")
                except Empty:
                    log.warning('Configurations plugin unavailable')
            except (KeyError, ValueError):
                raise Exception("Public project doesn't exist")

        except Empty:
            log.warning('Configurations plugin rpc not available')


