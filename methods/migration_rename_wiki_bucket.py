from pylon.core.tools import log
from pylon.core.tools import web

from tools import MinioClient


OLD_BUCKET = "wiki_artifacts"
NEW_BUCKET = "wiki-artifacts"


class Method:
    """
    Rename deepwiki_plugin's wiki_artifacts bucket to wiki-artifacts.

    S3 naming conventions disallow underscores. This task copies every object
    from `<project_prefix>wiki_artifacts` to `<project_prefix>wiki-artifacts`.
    The old bucket is left intact for safety; clean it up manually once the
    deepwiki_plugin code change is deployed and verified.

    Idempotent: re-running skips files already present in the target bucket.
    One-time migration: not needed once all environments have run it.

    Param format (optional):
        "project_id=<all|N>"
    Examples:
        ""                  -> all projects (default)
        "project_id=all"    -> all projects
        "project_id=42"     -> project 42 only
    """

    @web.method()
    def migration_rename_wiki_bucket(self, *args, **kwargs) -> dict:
        param = kwargs.get("param", "") or ""
        project_id_filter = None
        for seg in [s.strip() for s in param.split(";")]:
            if seg.lower().startswith("project_id="):
                value = seg[len("project_id="):].strip()
                if value.lower() != "all":
                    try:
                        project_id_filter = int(value)
                    except ValueError:
                        log.warning(
                            "migration_rename_wiki_bucket: invalid project_id '%s', scanning all",
                            value,
                        )

        results = {
            "success": True,
            "projects_processed": 0,
            "projects_with_old_bucket": 0,
            "files_copied": 0,
            "files_skipped": 0,
            "errors": [],
        }

        try:
            if project_id_filter is not None:
                project_list = [{"id": project_id_filter}]
            else:
                project_list = self.context.rpc_manager.timeout(30).project_list(
                    filter_={"create_success": True}
                )
            results["projects_processed"] = len(project_list)

            for project in project_list:
                project_id = project["id"]
                project_name = project.get("name", f"project_{project_id}")

                try:
                    mc = MinioClient(project)
                    buckets = mc.list_bucket()

                    if OLD_BUCKET not in buckets:
                        continue

                    results["projects_with_old_bucket"] += 1
                    log.info(
                        "[%s] migrating %s -> %s",
                        project_name, OLD_BUCKET, NEW_BUCKET,
                    )

                    mc.create_bucket(NEW_BUCKET)

                    existing_keys = {f["name"] for f in mc.list_files(NEW_BUCKET)}
                    old_files = mc.list_files(OLD_BUCKET)

                    for f in old_files:
                        key = f["name"]
                        if key in existing_keys:
                            results["files_skipped"] += 1
                            continue
                        try:
                            data = mc.download_file(OLD_BUCKET, key)
                            mc.upload_file(NEW_BUCKET, data, key)
                            results["files_copied"] += 1
                        except Exception as e:
                            error_msg = f"[{project_name}] failed to copy {key}: {str(e)}"
                            log.error(error_msg, exc_info=True)
                            results["errors"].append(error_msg)

                except Exception as e:
                    error_msg = f"[{project_name}] error during migration: {str(e)}"
                    log.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)

            log.info(
                "wiki_artifacts -> wiki-artifacts migration complete (filter=%s): "
                "%d projects scanned, %d had old bucket, %d files copied, %d skipped",
                project_id_filter if project_id_filter is not None else "all",
                results["projects_processed"],
                results["projects_with_old_bucket"],
                results["files_copied"],
                results["files_skipped"],
            )
            return results

        except Exception as e:
            error_msg = f"Critical error during migration: {str(e)}"
            log.error(error_msg, exc_info=True)
            results["success"] = False
            results["errors"].append(error_msg)
            return results
