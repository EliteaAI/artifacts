from pylon.core.tools import log
from pylon.core.tools import web


BEARER_LABEL_PREFIX = "Bearer - "


class Method:
    """
    Remove auto-created Bearer S3 credentials from non-personal projects.
    """

    @web.method()
    def migration_cleanup_bearer_s3_credentials(self, *args, **kwargs) -> dict:
        """Delete auto-created "Bearer - <user>" S3 credentials from team/public projects (R-2.0.7, #6914). Param: project_id=<all|N>[;dry_run]

        Bearer auth on the S3 API used to persist a credential in whatever project the request
        targeted. Bearer auth no longer needs it, so these rows are dropped from every project
        that is not a personal one.

        A credential is kept (and reported) when:
            - it has bucket_permissions: an admin restriction lives on it
            - it was rotated: its secret was handed out and may be used by an S3 client

        Personal projects and credentials with any other label are never touched.
        Idempotent: a second run finds nothing to delete.

        Param format (required):
            "project_id=<all|N>[;dry_run]"

        Examples:
            "project_id=all;dry_run"  - report what would be deleted across all projects
            "project_id=all"          - clean up all projects
            "project_id=3"            - clean up project 3 only
        """
        param = kwargs.get("param", "") or ""
        dry_run = False
        project_id_filter = None
        project_id_found = False

        for seg in [s.strip() for s in param.split(";")]:
            seg_lower = seg.lower()
            if seg_lower.startswith("project_id="):
                project_id_found = True
                value = seg[len("project_id="):].strip()
                if value.lower() != "all":
                    try:
                        project_id_filter = int(value)
                    except ValueError:
                        log.error("migration_cleanup_bearer_s3_credentials: invalid project_id '%s'", value)
                        return {"deleted": 0, "error": f"invalid project_id: '{value}'"}
            elif seg_lower == "dry_run":
                dry_run = True

        if not project_id_found:
            log.error("migration_cleanup_bearer_s3_credentials: project_id= is required. Format: project_id=<all|N>[;dry_run]")
            return {"deleted": 0, "error": "project_id= is required. Format: project_id=<all|N>[;dry_run]"}

        prefix = "[DRY RUN] " if dry_run else ""
        rpc = self.context.rpc_manager
        result = {
            "deleted": 0,
            "kept": {"bucket_permissions": 0, "rotated": 0},
            "personal_projects_skipped": 0,
            "failed_projects": [],
            "dry_run": dry_run,
        }

        try:
            if project_id_filter is not None:
                projects = [{"id": project_id_filter}]
            else:
                projects = rpc.timeout(30).project_list(filter_={"create_success": True}) or []
        except Exception:  # pylint: disable=W0703
            log.exception("migration_cleanup_bearer_s3_credentials: failed to list projects")
            return {"deleted": 0, "error": "failed to list projects"}

        for project in projects:
            project_id = project["id"]
            try:
                if rpc.timeout(5).projects_get_project_kind(project_id=project_id) == "personal":
                    result["personal_projects_skipped"] += 1
                    continue

                configs = rpc.timeout(10).configurations_get_filtered_project(
                    project_id=project_id,
                    include_shared=False,
                    filter_fields={"type": "s3_api_credentials"},
                ) or []

                for config in configs:
                    label = config.get("label") or ""
                    if not label.startswith(BEARER_LABEL_PREFIX):
                        continue
                    data = config.get("data") or {}

                    if data.get("bucket_permissions"):
                        reason = "bucket_permissions"
                    elif data.get("rotated_at"):
                        reason = "rotated"
                    else:
                        reason = None

                    if reason:
                        result["kept"][reason] += 1
                        log.info(
                            "%sproject %s: [KEEP:%s] credential id=%s '%s'",
                            prefix, project_id, reason, config.get("id"), label,
                        )
                        continue

                    log.info(
                        "%sproject %s: [DELETE] credential id=%s '%s' user_id=%s",
                        prefix, project_id, config.get("id"), label, data.get("user_id"),
                    )
                    if not dry_run and not rpc.timeout(10).configurations_delete(
                        project_id=project_id, config_id=config["id"]
                    ):
                        raise RuntimeError(f"configuration {config['id']} not found")
                    result["deleted"] += 1

            except Exception:  # pylint: disable=W0703
                log.exception("%smigration_cleanup_bearer_s3_credentials: error in project %s", prefix, project_id)
                result["failed_projects"].append(project_id)

        log.info(
            "%sExiting migration_cleanup_bearer_s3_credentials — %s %s credential(s), kept %s, "
            "personal projects skipped %s, failed projects %s",
            prefix, "would delete" if dry_run else "deleted", result["deleted"], result["kept"],
            result["personal_projects_skipped"], result["failed_projects"],
        )
        return result
