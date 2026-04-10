import urllib.parse

from flask import send_file, request
from io import BytesIO
from hurry.filesize import size
from pylon.core.tools import log
from botocore.exceptions import ClientError

from tools import MinioClient, api_tools, auth


class ProjectAPI(api_tools.APIModeHandler):
    @auth.decorators.check_api(["configuration.artifacts.artifacts.view"])
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

    @auth.decorators.check_api(["configuration.artifacts.artifacts.delete"])
    def delete(self, project_id: int, bucket: str):
        filename: str = request.args.get('filename')
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
        '<string:mode>/<string:project_id>/<string:bucket>',
        '<string:project_id>/<string:bucket>/<path:filename>',
        '<string:mode>/<string:project_id>/<string:bucket>/<path:filename>',
    ]

    mode_handlers = {
        'default': ProjectAPI,
    }
