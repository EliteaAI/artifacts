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

""" S3 API Methods """

from pylon.core.tools import log
from pylon.core.tools import web

from tools import context, this, auth


class Method:  # pylint: disable=E1101,R0903,W0201
    """
        S3 API Method Resource

        self is pointing to current Module instance

        web.method decorator takes zero or one argument: method name
        Note: web.method decorator must be the last decorator (at top)
    """

    @web.init()
    def s3_api_init(self):
        """Initialize S3 API - register public rule"""
        # Build the public rule pattern
        # Routes are mounted at /{module_name}/s3/ so S3 API will be at /artifacts/s3/...
        # The full path is: {context.url_prefix}/{module_name}/s3/...
        # Example: /artifacts/s3/bucket/key
        self.s3_public_rule = f"{context.url_prefix}/{this.module_name}/s3/.*"

        log.info("Registering S3 API public rule: %s", self.s3_public_rule)

        auth.add_public_rule({
            "uri": self.s3_public_rule,
        })

        log.info("S3-compatible API initialized at /%s/s3/ (uses AWS SigV4 authentication)",
                 this.module_name)

    @web.deinit()
    def s3_api_deinit(self):
        """Cleanup S3 API - remove public rule"""
        try:
            auth.remove_public_rule({
                "uri": self.s3_public_rule,
            })
            log.info("Removed S3 API public rule")
        except Exception:
            pass

    @web.method()
    def s3_get_credential(self, access_key_id: str):
        """
        Get S3 credential by access key ID.

        This is a method that can be called via self.s3_get_credential()
        from routes or other methods.
        """
        return self.context.rpc_manager.call.s3_credentials_get_by_access_key(
            access_key_id=access_key_id
        )
