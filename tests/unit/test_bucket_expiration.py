"""
Unit tests for rpc/bucket_expiration.py (P1 Step 6): the notifier must produce
identical notifications whether it's fed a precomputed `buckets_by_project` +
batched metas (the new shared-walk path) or falls back to its original
per-bucket mc.list_bucket()/get_bucket_lifecycle()/get_bucket_tags() calls.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fixtures.bucket_expiration_loader import load_bucket_expiration  # noqa: E402  pylint: disable=C0413

bucket_expiration = load_bucket_expiration()


def _tags_response(tags):
    return {"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]}


class _FakeMinioClient:
    """One instance per project; buckets/lifecycles/tags are shared across
    instances via the class-level dicts passed in at construction."""

    def __init__(self, project, buckets, lifecycles, tags_by_bucket, load_metas_enabled=True):
        self.project = project
        self._buckets = buckets
        self._lifecycles = lifecycles
        self._tags = tags_by_bucket
        self._load_metas_enabled = load_metas_enabled
        self.list_bucket_calls = 0
        self.get_bucket_lifecycle_calls = 0
        self.get_bucket_tags_calls = 0

    def list_bucket(self):
        self.list_bucket_calls += 1
        return list(self._buckets)

    def load_metas(self, buckets):
        if not self._load_metas_enabled:
            raise AttributeError("load_metas")
        return {
            b: {"lifecycle": self._lifecycles.get(b, {}).get("days"), "tags": dict(self._tags.get(b, {}))}
            for b in buckets
        }

    def get_bucket_lifecycle(self, bucket):
        self.get_bucket_lifecycle_calls += 1
        days = self._lifecycles.get(bucket, {}).get("days")
        if not days:
            return {}
        return {"Rules": [{"Expiration": {"Days": days}}]}

    def get_bucket_tags(self, bucket):
        self.get_bucket_tags_calls += 1
        return _tags_response(self._tags.get(bucket, {}))

    def set_bucket_tags(self, bucket, tags):
        self._tags[bucket] = dict(tags)


class _FakeTimeoutRpc:
    def __init__(self, projects, users_by_project):
        self._projects = projects
        self._users_by_project = users_by_project

    def project_list(self, filter_=None):  # pylint: disable=unused-argument
        return self._projects

    def admin_get_users_ids_in_project(self, project_id):
        return self._users_by_project.get(project_id, [])


class _FakeRpcManager:
    def __init__(self, projects, users_by_project):
        self._rpc = _FakeTimeoutRpc(projects, users_by_project)

    def timeout(self, _seconds):
        return self._rpc


class _FakeEventManager:
    def __init__(self):
        self.fired = []

    def fire_event(self, event_name, payload):
        self.fired.append((event_name, payload))


class _FakeContext:
    def __init__(self, projects, users_by_project):
        self.rpc_manager = _FakeRpcManager(projects, users_by_project)
        self.event_manager = _FakeEventManager()


def _make_rpc(projects, users_by_project):
    rpc = bucket_expiration.RPC()
    rpc.context = _FakeContext(projects, users_by_project)
    return rpc


def _expiring_tomorrow_tags():
    return {"expiration_date": (date.today() + timedelta(days=1)).isoformat()}


def _notified_pairs(context):
    return sorted(set(
        (payload["project_id"], payload["meta"]["bucket_name"])
        for _, payload in context.event_manager.fired
    ))


def test_prefetched_and_fallback_paths_notify_identical_pairs(monkeypatch):
    monkeypatch.setattr(bucket_expiration, "MinioClient", _FakeMinioClient)

    projects = [{"id": 1}, {"id": 2}]
    users_by_project = {1: [10, 11], 2: [20]}
    buckets = {1: ["b1"], 2: ["b2"]}
    lifecycles = {"b1": {"days": 30}, "b2": {"days": 30}}
    tags = {"b1": _expiring_tomorrow_tags(), "b2": _expiring_tomorrow_tags()}

    rpc_a = _make_rpc(projects, users_by_project)
    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, buckets[p["id"]], lifecycles, {k: dict(v) for k, v in tags.items()}),
    )
    buckets_by_project = {"1": ["b1"], "2": ["b2"]}
    rpc_a.check_bucket_expiration_notifications(buckets_by_project=buckets_by_project)
    notified_a = _notified_pairs(rpc_a.context)

    rpc_b = _make_rpc(projects, users_by_project)
    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, buckets[p["id"]], lifecycles, {k: dict(v) for k, v in tags.items()},
                                    load_metas_enabled=False),
    )
    rpc_b.check_bucket_expiration_notifications(buckets_by_project=None)
    notified_b = _notified_pairs(rpc_b.context)

    assert notified_a == notified_b == [(1, "b1"), (2, "b2")]


def test_buckets_by_project_restricts_to_precomputed_list(monkeypatch):
    buckets_seen = []

    def _minio_client(project):
        mc = _FakeMinioClient(project, buckets=["should-not-be-listed"], lifecycles={}, tags_by_bucket={})
        buckets_seen.append(mc)
        return mc

    monkeypatch.setattr(bucket_expiration, "MinioClient", _minio_client)

    rpc = _make_rpc([{"id": 1}], {})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": []})

    assert buckets_seen[0].list_bucket_calls == 0
    assert rpc.context.event_manager.fired == []


def test_metas_path_skips_get_bucket_lifecycle_and_reads_tags_from_meta(monkeypatch):
    """The read path (lifecycle + tags for the days-remaining check) should
    come entirely from the batched meta. The one get_bucket_tags call that
    remains is the read-modify-write in _update_bucket_tags when marking the
    bucket as notified -- unrelated to the read-side I/O this test targets."""
    mc_holder = {}

    def _minio_client(project):
        mc = _FakeMinioClient(
            project, buckets=["b1"], lifecycles={"b1": {"days": 30}},
            tags_by_bucket={"b1": _expiring_tomorrow_tags()},
        )
        mc_holder["mc"] = mc
        return mc

    monkeypatch.setattr(bucket_expiration, "MinioClient", _minio_client)

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    assert mc_holder["mc"].get_bucket_lifecycle_calls == 0
    assert mc_holder["mc"].get_bucket_tags_calls == 1
    assert len(rpc.context.event_manager.fired) == 1


def test_fallback_path_used_when_load_metas_missing(monkeypatch):
    mc_holder = {}

    def _minio_client(project):
        mc = _FakeMinioClient(
            project, buckets=["b1"], lifecycles={"b1": {"days": 30}},
            tags_by_bucket={"b1": _expiring_tomorrow_tags()}, load_metas_enabled=False,
        )
        mc_holder["mc"] = mc
        return mc

    monkeypatch.setattr(bucket_expiration, "MinioClient", _minio_client)

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project=None)

    assert mc_holder["mc"].list_bucket_calls == 1
    assert mc_holder["mc"].get_bucket_lifecycle_calls == 1
    # one read (tags for days-remaining check) + one read-modify-write (mark notified)
    assert mc_holder["mc"].get_bucket_tags_calls == 2
    assert len(rpc.context.event_manager.fired) == 1


def test_already_notified_bucket_is_skipped(monkeypatch):
    tags = _expiring_tomorrow_tags()
    tags["notified_warnings"] = "1"

    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, ["b1"], {"b1": {"days": 30}}, {"b1": tags}),
    )

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    assert rpc.context.event_manager.fired == []


def test_no_lifecycle_rules_skips_bucket(monkeypatch):
    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, ["b1"], {}, {"b1": _expiring_tomorrow_tags()}),
    )

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    assert rpc.context.event_manager.fired == []


def test_days_remaining_not_one_skips_bucket(monkeypatch):
    tags = {"expiration_date": (date.today() + timedelta(days=5)).isoformat()}
    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, ["b1"], {"b1": {"days": 30}}, {"b1": tags}),
    )

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    assert rpc.context.event_manager.fired == []


def test_notified_warnings_tag_updated_after_notification(monkeypatch):
    mc_holder = {}

    def _minio_client(project):
        mc = _FakeMinioClient(project, ["b1"], {"b1": {"days": 30}}, {"b1": _expiring_tomorrow_tags()})
        mc_holder["mc"] = mc
        return mc

    monkeypatch.setattr(bucket_expiration, "MinioClient", _minio_client)

    rpc = _make_rpc([{"id": 1}], {1: [10]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    assert mc_holder["mc"]._tags["b1"]["notified_warnings"] == "1"


def test_fires_one_event_per_user_in_project(monkeypatch):
    monkeypatch.setattr(
        bucket_expiration, "MinioClient",
        lambda p: _FakeMinioClient(p, ["b1"], {"b1": {"days": 30}}, {"b1": _expiring_tomorrow_tags()}),
    )

    rpc = _make_rpc([{"id": 1}], {1: [10, 11, 12]})
    rpc.check_bucket_expiration_notifications(buckets_by_project={"1": ["b1"]})

    user_ids = [payload["user_id"] for _, payload in rpc.context.event_manager.fired]
    assert sorted(user_ids) == [10, 11, 12]
