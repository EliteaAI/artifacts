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

""" RPC methods for artifact operations """

from typing import Optional

from hurry.filesize import size
from tools import MinioClient, api_tools
from pylon.core.tools import log, web

from ..utils.utils import parse_filepath, make_filepath


class RPC:
    @web.rpc('artifacts_get_file_data', 'get_file_data')
    def get_file_data(
        self,
        project_id: int,
        filepath: str = None,
        bucket: str = None,
        filename: str = None,
        configuration_title: Optional[str] = None
    ) -> Optional[dict]:
        """
        Get file data from MinIO by filepath or bucket+filename.

        Args:
            project_id: Project ID
            filepath: File path in format /{bucket}/{filename} (alternative to bucket+filename)
            bucket: Bucket name (used if filepath not provided)
            filename: File name (used if filepath not provided)
            configuration_title: Optional S3 configuration title

        Returns:
            dict with bucket, filename, file_data (bytes) or None if not found

        NOTE: Do not use across different pylons
        """
        try:
            # Parse filepath if provided, otherwise use bucket+filename
            if filepath:
                bucket, filename = parse_filepath(filepath)
            
            if not bucket or not filename:
                log.warning("Either filepath or bucket+filename must be provided")
                return None

            project = self.context.rpc_manager.timeout(3).project_get_or_404(project_id=project_id)
            mc = MinioClient(project, configuration_title=configuration_title)
            
            file_data = mc.download_file(bucket, filename)
            
            if file_data is None:
                log.warning(f"File not found: {bucket}/{filename}")
                return None

            return {
                "filepath": make_filepath(bucket, filename),
                "bucket": bucket,
                "filename": filename,
                "file_data": file_data
            }
        except Exception as e:
            log.error(f"Error getting file data for {filepath or f'{bucket}/{filename}'}: {e}")
            return None

    @web.rpc('artifacts_upload', 'upload_artifact')
    def upload_artifact(
        self,
        project_id: int,
        bucket: str,
        filename: str,
        file_data: bytes,
        configuration_title: Optional[str] = None,
        create_if_not_exists: bool = True,
        bucket_retention_days: Optional[int] = None,
        check_duplicates: bool = True,
        overwrite: bool = False
    ) -> dict:
        """
        Upload file to MinIO.
        
        Handles all MinIO operations:
        - Bucket creation (if needed)
        - Duplicate file checking (unless overwrite=True)
        - File upload

        Args:
            project_id: Project ID
            bucket: Bucket name
            filename: File name
            file_data: File content bytes
            configuration_title: Optional S3 configuration title
            create_if_not_exists: Create bucket if it doesn't exist
            bucket_retention_days: Retention policy for bucket (if creating)
            check_duplicates: Check for duplicate files (unless overwrite=True)
            overwrite: Allow overwriting existing files

        Returns:
            dict with bucket, filename, size, was_duplicate

        Raises:
            RuntimeError: If duplicate file exists and overwrite=False

        NOTE: Do not use across different pylons
        """
        try:
            project = self.context.rpc_manager.timeout(3).project_get_or_404(project_id=project_id)
            mc = MinioClient(project, configuration_title=configuration_title)
            
            was_duplicate = False

            # Check for duplicates if requested and not overwriting
            if check_duplicates and not overwrite:
                try:
                    bucket_files = mc.list_files(bucket)
                    if any(bf['name'] == filename for bf in bucket_files):
                        was_duplicate = True
                        raise RuntimeError(f"File '{filename}' already exists in bucket '{bucket}'")
                except Exception as list_error:
                    # If bucket doesn't exist, list_files will fail - that's okay
                    if "already exists" in str(list_error):
                        raise  # Re-raise duplicate error
                    # Otherwise, bucket doesn't exist yet - continue
                    pass
            
            # Create bucket if it doesn't exist
            if create_if_not_exists and bucket not in mc.list_bucket():
                mc.create_bucket(
                    bucket=bucket,
                    bucket_type='local',
                    retention_days=bucket_retention_days
                )

            # Upload file to MinIO
            api_tools.upload_file_base(
                bucket=bucket,
                data=file_data,
                file_name=filename,
                client=mc,
                create_if_not_exists=False  # Already handled above
            )

            # Get uploaded file size in bytes
            file_size_bytes = mc.get_file_size(bucket, filename) if filename else 0

            log.info(f"Uploaded file {bucket}/{filename}")

            return {
                "filepath": make_filepath(bucket, filename),
                "bucket": bucket,
                "filename": filename,
                "size": size(file_size_bytes),
                "was_duplicate": was_duplicate
            }
        except Exception as e:
            log.error(f"Failed to upload artifact: {e}")
            raise
