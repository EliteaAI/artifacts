from pylon.core.tools import web, log

from ..models.pd.configuration import configuration_record


class Event:
    @web.event('configuration_created')
    def configuration_created(self, context, event, payload: dict):
        configuration_type = payload['type']
        if configuration_type == configuration_record['type_name']:
            context.rpc_manager.call.configurations_update(
                project_id=payload['project_id'],
                config_id=payload['id'],
                payload={'status_ok': True}
            )