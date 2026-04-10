from flask import request

from hurry.filesize import size

from tools import MinioClient, api_tools, auth
from pylon.core.tools import log

from ...utils.utils import make_filepath


def calculate_readable_retention_policy(days: int) -> dict:
    """Convert days to human-readable retention policy."""
    if days and days % 365 == 0:
        expiration_measure, expiration_value = 'years', days // 365
    elif days and days % 31 == 0:
        expiration_measure, expiration_value = 'months', days // 31
    elif days and days % 7 == 0:
        expiration_measure, expiration_value = 'weeks', days // 7
    else:
        expiration_measure, expiration_value = 'days', days
    return {
        'expiration_measure': expiration_measure,
        'expiration_value': expiration_value
    }


class ProjectAPI(api_tools.APIModeHandler):
    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.artifacts.view"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": True, "editor": True},
            "default": {"admin": True, "viewer": True, "editor": True},
            "developer": {"admin": True, "viewer": True, "editor": True},
        }})
    def get(self, project_id: int, bucket: str):
        """List files in bucket with filepath."""
        project = self.module.context.rpc_manager.call.project_get_or_404(project_id=project_id)
        configuration_title = request.args.get('configuration_title')
        mc = MinioClient(project, configuration_title=configuration_title)
        try:
            lifecycle = mc.get_bucket_lifecycle(bucket)
            retention_policy = calculate_readable_retention_policy(
                days=lifecycle["Rules"][0]['Expiration']['Days']
            )
        except Exception:
            retention_policy = None
        try:
            files = mc.list_files(bucket)

            # Format size for each file
            for each in files:
                each["size"] = size(each["size"])

            return {"retention_policy": retention_policy, "total": len(files), "rows": files}
        except Exception as e:
            return {"error": str(e)}, 400

    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.artifacts.create"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
            "developer": {"admin": True, "viewer": False, "editor": True},
        }})
    def post(self, project_id: int, bucket: str):
        """Upload file and return filepath."""
        configuration_title = request.args.get('configuration_title')

        if "file" not in request.files:
            return {'error': 'No file provided'}, 400

        file = request.files["file"]
        filename = file.filename
        file_data = file.read()

        try:
            # Call upload_artifact RPC directly within same pylon
            result = self.module.upload_artifact(
                project_id=project_id,
                bucket=bucket,
                filename=filename,
                file_data=file_data,
                configuration_title=configuration_title,
                create_if_not_exists=request.args.get('create_if_not_exists', True),
                overwrite=request.args.get('overwrite', 'true').lower() == 'true'
            )

            # Build response with appropriate message
            message = "Overwritten" if result.get("was_duplicate") else "Done"
            response = {
                "message": message,
                "ok": True,
                "filepath": make_filepath(result["bucket"], result["filename"]),
                "bucket": result["bucket"],
                "filename": result["filename"],
                "size": result["size"]
            }

            return response, 200

        except AttributeError as e:
            return {'error': f'Error accessing s3: {configuration_title}'}, 400
        except Exception as e:
            log.error(f"Upload failed: {e}")
            return {'error': str(e)}, 500

    @auth.decorators.check_api({
        "permissions": ["configuration.artifacts.artifacts.delete"],
        "recommended_roles": {
            "administration": {"admin": True, "viewer": False, "editor": True},
            "default": {"admin": True, "viewer": False, "editor": True},
            "developer": {"admin": True, "viewer": False, "editor": True},
        }})
    def delete(self, project_id: int, bucket: str):
        """
        Delete file(s) from bucket.
        
        Query params:
        - fname[]: filename(s) to delete
        """
        args = request.args
        project = self.module.context.rpc_manager.call.project_get_or_404(project_id=project_id)
        configuration_title = args.get('configuration_title')

        try:
            mc = MinioClient(project, configuration_title=configuration_title)
        except AttributeError:
            return {'error': f'Error accessing s3: {configuration_title}'}, 400

        # Get filenames to delete
        filenames = args.getlist("fname[]")

        # Delete from S3
        if not filenames:
            mc.remove_bucket(bucket)
        else:
            for fname in filenames:
                mc.remove_file(bucket, fname)

        return {"message": "Deleted", "size": size(mc.get_bucket_size(bucket))}, 200


class API(api_tools.APIBase):
    url_params = [
        '<string:project_id>/<string:bucket>',
        '<string:mode>/<string:project_id>/<string:bucket>',
    ]

    mode_handlers = {
        'default': ProjectAPI,
    }
