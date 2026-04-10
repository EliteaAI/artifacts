from datetime import date

from pylon.core.tools import web, log

from tools import MinioClient


def _update_bucket_tags(mc, bucket, new_tags):
    response = mc.get_bucket_tags(bucket)
    existing_tags = {
        tag['Key']: tag['Value']
        for tag in response.get('TagSet', [])
    } if response else {}
    existing_tags.update(new_tags)
    mc.set_bucket_tags(bucket=bucket, tags=existing_tags)


class RPC:
    @web.rpc('artifacts_check_bucket_expiration_notifications')
    def check_bucket_expiration_notifications(self):
        try:
            project_list = self.context.rpc_manager.timeout(30).project_list(
                filter_={'create_success': True}
            )
        except Exception as e:
            log.warning('Failed to get project list for bucket expiration check: %s', e)
            return

        today = date.today()

        for project in project_list:
            project_id = project['id']
            try:
                mc = MinioClient(project)
                buckets = mc.list_bucket()
            except Exception as e:
                log.warning('Failed to access MinIO for project %s: %s', project_id, e)
                continue

            for bucket in buckets:
                try:
                    lifecycle = mc.get_bucket_lifecycle(bucket)
                    rules = lifecycle.get('Rules', [])
                    if not rules:
                        continue

                    total_days = rules[0].get('Expiration', {}).get('Days')
                    if not total_days:
                        continue

                    tag_response = mc.get_bucket_tags(bucket)
                    tags = {
                        tag['Key']: tag['Value']
                        for tag in tag_response.get('TagSet', [])
                    } if tag_response else {}

                    expiration_date_str = tags.get('expiration_date')
                    if not expiration_date_str:
                        continue

                    expiration_date = date.fromisoformat(expiration_date_str)
                    days_remaining = (expiration_date - today).days

                    if days_remaining != 1:
                        continue

                    notified = set(filter(None, tags.get('notified_warnings', '').split(',')))
                    if '1' in notified:
                        continue

                    try:
                        user_ids = self.context.rpc_manager.timeout(5).admin_get_users_ids_in_project(
                            project_id
                        )
                    except Exception as e:
                        log.warning('Failed to get users for project %s: %s', project_id, e)
                        continue

                    for user_id in user_ids:
                        self.context.event_manager.fire_event(
                            'notifications_stream', {
                                'project_id': project_id,
                                'user_id': user_id,
                                'meta': {
                                    'bucket_name': bucket,
                                    'expiration_date': expiration_date.isoformat(),
                                    'days_remaining': days_remaining,
                                    'warning_threshold': 1,
                                },
                                'event_type': 'bucket_expiration_warning',
                            }
                        )

                    notified.add('1')
                    _update_bucket_tags(mc, bucket, {
                        'notified_warnings': ','.join(sorted(notified)),
                    })
                except Exception as e:
                    log.warning(
                        'Error processing bucket %s in project %s: %s',
                        bucket, project_id, e
                    )
