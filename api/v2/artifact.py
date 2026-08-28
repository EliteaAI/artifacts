import urllib.parse

from flask import send_file, request
from io import BytesIO
from hurry.filesize import size
from pylon.core.tools import log
from botocore.exceptions import ClientError

from tools import MinioClient, api_tools, auth, register_openapi

from ...utils.utils import require_bucket_write_permission, require_bucket_read_permission


class ProjectAPI(api_tools.APIModeHandler):
    @register_openapi(
        name="Download Artifact",
        description="Download a file from a project bucket.",
        mcp_tool=True,
        mcp_description="Use this tool when you need the actual contents of one known file and already know its bucket and exact filename/path. Do not use this tool to browse bucket contents, discover filenames, or upload files — use List Artifacts or Upload Artifact instead. Do not use for whole-bucket operations. This tool is best for 'fetch this file now' scenarios after the file has already been discovered elsewhere.",
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
            {"name": "bucket", "in": "path", "schema": {"type": "string"},
             "description": "Bucket name."},
            {"name": "filename", "in": "path", "schema": {"type": "string"},
             "description": "File path within the bucket (URL-encoded)."},
            {"name": "configuration_title", "in": "query", "schema": {"type": "string"},
             "description": "Optional S3 configuration title override."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api(["configuration.artifacts.artifacts.view"])
    @require_bucket_read_permission(lambda req, **kw: kw.get('bucket'))
    def get(self, project_id: int, bucket: str, filename: str):
        project = self.module.context.rpc_manager.call.project_get_or_404(project_id=project_id)
        configuration_title = request.args.get('configuration_title')
        try:
            mc = MinioClient(project, configuration_title=configuration_title)
        except AttributeError:
            return {'error': f'Error accessing s3: {configuration_title}'}, 400
        try:
            file = mc.download_file(bucket, filename)
        except:  # pylint: disable=W0702
            log.warning('File %s/%s was not found in project bucket. Looking in admin...', bucket, filename)
            return {'error': 'File was not found'}, 400
        try:
            return send_file(BytesIO(file), attachment_filename=filename)
        except TypeError:  # new flask
            return send_file(BytesIO(file), download_name=filename, as_attachment=False)

    @register_openapi(
        name="Rename Artifact",
        description="Rename a file in a project bucket.",
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
            {"name": "bucket", "in": "path", "schema": {"type": "string"},
             "description": "Bucket name."},
            {"name": "old_name", "in": "query", "schema": {"type": "string"},
             "required": True,
             "description": "Current filename (URL-encoded)."},
            {"name": "new_name", "in": "query", "schema": {"type": "string"},
             "required": True,
             "description": "New filename (URL-encoded)."},
            {"name": "configuration_title", "in": "query", "schema": {"type": "string"},
             "description": "Optional S3 configuration title override."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api(["configuration.artifacts.artifacts.edit"])
    @require_bucket_write_permission(lambda req, **kw: kw.get('bucket'))
    def put(self, project_id: int, bucket: str):
        old_name: str = request.args.get('old_name')
        new_name: str = request.args.get('new_name')
        if not old_name or not new_name:
            return {'error': 'old_name and new_name query parameters are required'}, 400
        decoded_old_name: str = urllib.parse.unquote(old_name)
        decoded_new_name: str = urllib.parse.unquote(new_name)

        if decoded_old_name == decoded_new_name:
            return {'error': 'old_name and new_name must be different'}, 400

        project = self.module.context.rpc_manager.call.project_get_or_404(project_id=project_id)
        configuration_title = request.args.get('configuration_title')
        try:
            mc = MinioClient(project, configuration_title=configuration_title)
        except AttributeError:
            return {'error': f'Error accessing s3: {configuration_title}'}, 400

        # Pre-flight checks to provide clear error messages
        if not mc.is_file_exist(bucket, decoded_old_name):
            return {'error': f'Source file not found: {decoded_old_name}'}, 404

        if mc.is_file_exist(bucket, decoded_new_name):
            return {'error': f'Destination file already exists: {decoded_new_name}'}, 409

        try:
            mc.rename_file(bucket, decoded_old_name, decoded_new_name)
        except FileNotFoundError as e:
            log.error('Source file not found when renaming %s to %s: %s', decoded_old_name, decoded_new_name, e)
            return {'error': f'Source file not found: {decoded_old_name}'}, 404
        except FileExistsError as e:
            log.error('Destination file exists when renaming %s to %s: %s', decoded_old_name, decoded_new_name, e)
            return {'error': f'Destination file already exists: {decoded_new_name}'}, 409
        except ClientError as e:
            log.error('Error renaming file %s to %s: %s', decoded_old_name, decoded_new_name, e)
            return {'error': 'Failed to rename file'}, 400
        except ValueError as e:
            log.error('Validation error renaming file %s to %s: %s', decoded_old_name, decoded_new_name, e)
            return {'error': str(e)}, 400
        except Exception as e:
            log.error('Unexpected error renaming file %s to %s: %s', decoded_old_name, decoded_new_name, e)
            return {'error': f'Failed to rename file: {str(e)}'}, 500

        return {"message": "Renamed", "old_name": decoded_old_name, "new_name": decoded_new_name}, 200

    @register_openapi(
        name="Delete Artifact",
        description="Delete a specific file from a project bucket.",
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"},
             "description": "Project identifier."},
            {"name": "bucket", "in": "path", "schema": {"type": "string"},
             "description": "Bucket name."},
            {"name": "filename", "in": "query", "schema": {"type": "string"},
             "required": True,
             "description": "URL-encoded filename to delete."},
            {"name": "configuration_title", "in": "query", "schema": {"type": "string"},
             "description": "Optional S3 configuration title override."},
        ],
        available_to_users=True,
    )
    @auth.decorators.check_api(["configuration.artifacts.artifacts.delete"])
    @require_bucket_write_permission(lambda req, **kw: kw.get('bucket'))
    def delete(self, project_id: int, bucket: str):
        filename: str = request.args.get('filename')
        if not filename:
            return {'error': 'filename query parameter is required'}, 400
        decoded_filename: str = urllib.parse.unquote(filename)

        project = self.module.context.rpc_manager.call.project_get_or_404(project_id=project_id)
        configuration_title = request.args.get('configuration_title')
        try:
            mc = MinioClient(project, configuration_title=configuration_title)
        except AttributeError:
            return {'error': f'Error accessing s3: {configuration_title}'}, 400

        # Delete from S3
        mc.remove_file(bucket, decoded_filename)

        return {"message": "Deleted", "size": size(mc.get_bucket_size(bucket))}, 200



class API(api_tools.APIBase):
    url_params = [
        '<string:mode>/<int:project_id>/<string:bucket>',
        '<int:project_id>/<string:bucket>/<path:filename>',
        '<string:mode>/<int:project_id>/<string:bucket>/<path:filename>',
    ]

    mode_handlers = {
        'default': ProjectAPI,
    }
