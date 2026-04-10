from pylon.core.tools import web, log  # pylint: disable=E0611,E0401
from tools import auth, theme  # pylint: disable=E0401


class Slot:  # pylint: disable=E1101,R0903
    @web.slot('administration_artifacts_content')
    @auth.decorators.check_slot(["configuration.artifacts"], 
                                access_denied_reply=theme.access_denied_part)
    def content(self, context, slot, payload):
        log.info('slot: [%s], payload: %s', slot, payload)
        with context.app.app_context():
            return self.descriptor.render_template(
                'artifacts/content.html'
            )

    @web.slot('administration_artifacts_scripts')
    @auth.decorators.check_slot(["configuration.artifacts"])
    def scripts(self, context, slot, payload):
        log.info('slot: [%s], payload: %s', slot, payload)
        with context.app.app_context():
            return self.descriptor.render_template(
                'artifacts/scripts.html',
            )

    @web.slot('administration_artifacts_styles')
    @auth.decorators.check_slot(["configuration.artifacts"])
    def styles(self, context, slot, payload):
        log.info('slot: [%s], payload: %s', slot, payload)
        with context.app.app_context():
            return self.descriptor.render_template(
                'artifacts/styles.html',
            )
