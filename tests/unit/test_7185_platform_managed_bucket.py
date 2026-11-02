"""#7185: every project's skill-files bucket holds that project's skill files, so the artifacts surface leaves it alone."""
import importlib
import sys
import types
from pathlib import Path

import pytest

ARTIFACTS_ROOT = Path(__file__).resolve().parents[2]
PKG = 'artifacts_7185'
MANAGED_ERROR = {'error': 'This bucket is managed by the platform'}, 403


def _passthrough(*args, **kwargs):
    return lambda func: func


class FakeRequest:
    def __init__(self):
        self.args = {}
        self.json = {}
        self.method = 'GET'
        self.headers = {}


class FakeMinioClient:
    """Two buckets of one project, no lifecycle on either."""

    def __init__(self, project, configuration_title=None):
        self.project = project
        self.lifecycles = {}
        self.removed = []
        self.created = []
        self.read = []
        self.written = []
        INSTANCES.append(self)

    def list_bucket(self):
        return ['skill-files', 'reports']

    def get_bucket_lifecycle(self, bucket):
        return None

    def configure_bucket_lifecycle(self, bucket, days):
        self.lifecycles[bucket] = days

    def get_bucket_size(self, bucket):
        return 0

    def get_bucket_tags(self, bucket):
        return None

    def format_bucket_name(self, bucket):
        return f"p--{self.project['id']}.{bucket}"

    def remove_bucket(self, bucket):
        self.removed.append(bucket)

    def create_bucket(self, bucket, bucket_type=None, retention_days=None):
        self.created.append(bucket)
        return {'Location': bucket}

    def download_file(self, bucket, file_name):
        self.read.append((bucket, file_name))
        return b'object'

    def upload_file(self, bucket, data, file_name):
        self.written.append((bucket, file_name))


INSTANCES = []


def _package(monkeypatch, name, path):
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    monkeypatch.setitem(sys.modules, name, package)


@pytest.fixture
def artifacts(monkeypatch):
    """The real utils, migration, bucket API and S3 modules with flask, auth and storage stubbed."""
    INSTANCES.clear()
    request = FakeRequest()
    tools = sys.modules['tools']
    monkeypatch.setattr(tools, 'MinioClient', FakeMinioClient)
    monkeypatch.setattr(tools, 'VaultClient', object, raising=False)
    monkeypatch.setattr(tools, 'context', types.SimpleNamespace(), raising=False)
    monkeypatch.setattr(tools, 'auth', types.SimpleNamespace(
        current_user=lambda: {'id': 5}, decorators=types.SimpleNamespace(check_api=_passthrough),
    ), raising=False)
    monkeypatch.setattr(tools, 'api_tools', types.SimpleNamespace(APIModeHandler=object, APIBase=object), raising=False)
    monkeypatch.setattr(tools, 'register_openapi', _passthrough, raising=False)
    monkeypatch.setattr(sys.modules['pylon.core.tools'].web, 'method', _passthrough, raising=False)
    monkeypatch.setattr(sys.modules['pylon.core.tools'].web, 'route', _passthrough, raising=False)
    monkeypatch.setitem(sys.modules, 'flask', types.SimpleNamespace(
        request=request, Response=object, g=types.SimpleNamespace()))
    monkeypatch.setitem(sys.modules, 'werkzeug', types.ModuleType('werkzeug'))
    monkeypatch.setitem(sys.modules, 'werkzeug.exceptions', types.SimpleNamespace(Forbidden=Exception))
    monkeypatch.setitem(sys.modules, 'dateutil', types.ModuleType('dateutil'))
    monkeypatch.setitem(sys.modules, 'dateutil.relativedelta', types.SimpleNamespace(relativedelta=dict))
    monkeypatch.setitem(sys.modules, 'hurry', types.ModuleType('hurry'))
    monkeypatch.setitem(sys.modules, 'hurry.filesize', types.SimpleNamespace(size=str))
    for name, path in (('', ''), ('.utils', 'utils'), ('.methods', 'methods'), ('.api', 'api'),
                       ('.api.v2', 'api/v2'), ('.models', 'models'), ('.models.pd', 'models/pd'),
                       ('.s3', 's3'), ('.s3.handlers', 's3/handlers'), ('.routes', 'routes')):
        _package(monkeypatch, PKG + name, ARTIFACTS_ROOT / path)
    monkeypatch.setitem(sys.modules, f'{PKG}.models.pd.api_models', types.SimpleNamespace(
        BucketCreateRequest=object, BucketUpdateRequest=object, BucketPatchRequest=object,
    ))
    modules = {}
    for name in ('utils.utils', 'methods.buckets_migration', 'api.v2.buckets', 's3.handlers.bucket',
                 's3.handlers.object', 'routes.s3'):
        monkeypatch.delitem(sys.modules, f'{PKG}.{name}', raising=False)
        modules[name] = importlib.import_module(f'{PKG}.{name}')
        monkeypatch.setitem(sys.modules, f'{PKG}.{name}', modules[name])
    modules['request'] = request
    return modules


def _rpc(project):
    return types.SimpleNamespace(context=types.SimpleNamespace(rpc_manager=types.SimpleNamespace(
        call=types.SimpleNamespace(
            project_get_or_404=lambda project_id: project,
            admin_check_user_is_admin=lambda project_id, user_id: True,
        ),
    )))


def _bucket_api(artifacts, project_id):
    api = artifacts['api.v2.buckets'].ProjectAPI()
    api.module = _rpc({'id': project_id})
    return api


@pytest.mark.parametrize('project_id, bucket, managed', [
    (1, 'skill-files', True),
    (2, 'skill-files', True),
    (7, 'skill-files', True),
    (2, 'p--2.skill-files', True),
    (2, 'p--1.skill-files', False),
    (2, 'reports', False),
    (2, None, False),
])
def test_every_project_skill_files_bucket_is_platform_managed(artifacts, project_id, bucket, managed):
    assert artifacts['utils.utils'].is_platform_managed_bucket(project_id, bucket) is managed


@pytest.mark.parametrize('decorator', ['require_bucket_write_permission', 'require_bucket_read_permission'])
@pytest.mark.parametrize('project_id', [1, 2])
def test_the_artifact_endpoints_refuse_the_skill_files_bucket(artifacts, monkeypatch, decorator, project_id):
    utils = artifacts['utils.utils']
    monkeypatch.setattr(utils, 'check_bucket_permission', lambda *args: True)
    calls = []
    handler = getattr(utils, decorator)(lambda req, **kw: kw.get('bucket'))(
        lambda self, project_id, bucket: calls.append((project_id, bucket)) or ({}, 200))

    assert handler(None, project_id, bucket='skill-files') == MANAGED_ERROR
    assert handler(None, project_id, bucket='reports') == ({}, 200)
    assert calls == [(project_id, 'reports')]


def test_the_retention_migration_never_gives_a_skill_files_bucket_an_expiry(artifacts):
    method = artifacts['methods.buckets_migration'].Method()
    method.context = types.SimpleNamespace(rpc_manager=types.SimpleNamespace(
        timeout=lambda seconds: types.SimpleNamespace(project_list=lambda filter_: [{'id': 1}, {'id': 2}]),
    ))

    results = method.migrate_artifact_buckets_retention()

    public, team = INSTANCES
    assert public.lifecycles == {'reports': 365}
    assert team.lifecycles == {'reports': 365}
    assert (results['buckets_updated'], results['buckets_skipped']) == (2, 2)


@pytest.mark.parametrize('project_id', [1, 2])
def test_the_bucket_list_hides_the_skill_files_bucket(artifacts, project_id):
    body, status = _bucket_api(artifacts, project_id).get(project_id)

    assert status == 200
    assert [row['name'] for row in body['rows']] == ['reports']


@pytest.mark.parametrize('project_id', [1, 2])
def test_the_skill_files_bucket_can_not_be_deleted(artifacts, project_id):
    artifacts['request'].args = {'name': 'skill-files'}

    assert _bucket_api(artifacts, project_id).delete(project_id) == MANAGED_ERROR
    assert INSTANCES == []

    artifacts['request'].args = {'name': 'reports'}
    _bucket_api(artifacts, project_id).delete(project_id)
    assert INSTANCES[0].removed == ['reports']


def test_a_user_can_not_create_the_skill_files_bucket_before_the_platform_does(artifacts):
    artifacts['request'].json = {'name': 'Skill-Files'}

    assert _bucket_api(artifacts, 2).post(2) == MANAGED_ERROR
    assert INSTANCES == []


def test_the_s3_bucket_list_hides_the_skill_files_bucket(artifacts, monkeypatch):
    bucket_module = artifacts['s3.handlers.bucket']
    listed = []
    monkeypatch.setattr(bucket_module, 'list_buckets_response', lambda buckets, **kw: listed.extend(buckets))

    bucket_module.BucketHandler(types.SimpleNamespace(id=2)).list_buckets()

    assert [bucket['name'] for bucket in listed] == ['reports']


@pytest.fixture
def s3_route(artifacts, monkeypatch):
    """The S3 route with a project-2 credential that has no bucket restrictions."""
    routes = artifacts['routes.s3']
    monkeypatch.setattr(routes, 'verify_s3_auth', lambda req: {'credential': {
        'project_id': 2, 'user_id': 5, 'bucket_permissions': {}}})
    monkeypatch.setattr(routes, 'responses', types.SimpleNamespace(
        error_response=lambda code, message, status_code: (code, message, status_code)))
    served = []

    class Handler:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args: served.append((name, args)) or 'served'

    for name in ('BucketHandler', 'ObjectHandler', 'MultipartHandler'):
        monkeypatch.setattr(routes, name, Handler)
    route = routes.Route()
    route.context = _rpc({'id': 2}).context
    route.served = served
    return route


@pytest.mark.parametrize('method, operation', [
    ('GET', 's3_object_operations'), ('DELETE', 's3_object_operations'), ('PUT', 's3_object_operations'),
    ('GET', 's3_bucket_operations'), ('DELETE', 's3_bucket_operations'), ('PUT', 's3_bucket_operations'),
])
def test_the_s3_gateway_refuses_the_skill_files_bucket(artifacts, s3_route, method, operation):
    artifacts['request'].method = method
    args = ('skill-files', 'abc123') if operation == 's3_object_operations' else ('skill-files',)

    assert getattr(s3_route, operation)(*args) == ('AccessDenied', 'Access denied to this bucket', 403)
    assert s3_route.served == []

    getattr(s3_route, operation)('reports', *args[1:])
    assert len(s3_route.served) == 1


@pytest.mark.parametrize('copy_source', ['/skill-files/abc123', 'p--2.skill-files/abc123'])
def test_the_s3_gateway_refuses_to_copy_out_of_the_skill_files_bucket(artifacts, s3_route, monkeypatch, copy_source):
    object_module = artifacts['s3.handlers.object']
    monkeypatch.setattr(object_module, 'error_response',
                        lambda code, message, status_code, resource=None: (code, message, status_code))
    monkeypatch.setattr(object_module, 'copy_object_response', lambda **kwargs: 'copied')
    monkeypatch.setattr(artifacts['routes.s3'], 'ObjectHandler', object_module.ObjectHandler)
    artifacts['request'].method = 'PUT'
    artifacts['request'].headers = {'x-amz-copy-source': copy_source}

    assert s3_route.s3_object_operations('reports', 'copy') == (
        'AccessDenied', 'Access denied to source bucket', 403)
    assert INSTANCES[-1].read == [] and INSTANCES[-1].written == []

    artifacts['request'].headers = {'x-amz-copy-source': '/reports/abc123'}
    assert s3_route.s3_object_operations('reports', 'copy') == 'copied'
    assert INSTANCES[-1].read == [('reports', 'abc123')] and INSTANCES[-1].written == [('reports', 'copy')]


def test_the_s3_gateway_refuses_to_move_into_or_out_of_the_skill_files_bucket(s3_route):
    assert s3_route.s3_move_objects('skill-files', 'abc123', 'reports', 'x')[2] == 403
    assert s3_route.s3_move_objects('reports', 'x', 'skill-files', 'abc123')[2] == 403
    assert s3_route.served == []
