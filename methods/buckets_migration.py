from pylon.core.tools import log
from pylon.core.tools import web

from tools import MinioClient


class Method:
    """
    Artifact buckets retention policy migration

    Purpose: Update existing artifact buckets to ensure minimum 1-year retention policy
    and reset file modification times to prevent immediate deletion.
    """

    @web.method()
    def migrate_artifact_buckets_retention(self, *args, **kwargs) -> dict:
        """
        Migrate artifact buckets to enforce minimum 1-year retention policy
        """
        MIN_RETENTION_DAYS = 365
        results = {
            "success": True,
            "projects_processed": 0,
            "buckets_updated": 0,
            "buckets_skipped": 0,
            "files_touched": 0,
            "errors": []
        }

        try:
            project_list = self.context.rpc_manager.timeout(30).project_list(
                filter_={"create_success": True}
            )
            results["projects_processed"] = len(project_list)

            for project in project_list:
                project_id = project["id"]
                project_name = project.get("name", f"project_{project_id}")

                try:
                    log.info(f"Processing project {project_id} ({project_name})")
                    mc = MinioClient(project)
                    buckets = mc.list_bucket()

                    for bucket in buckets:
                        try:
                            lifecycle = mc.get_bucket_lifecycle(bucket)

                            current_days = None
                            if lifecycle and "Rules" in lifecycle:
                                current_days = lifecycle["Rules"][0]["Expiration"]["Days"]

                            needs_update = False
                            if current_days is None:
                                log.info(f"Bucket {bucket}: No retention policy set, setting to {MIN_RETENTION_DAYS} days")
                                needs_update = True
                            elif current_days < MIN_RETENTION_DAYS:
                                log.info(f"Bucket {bucket}: Current retention {current_days} days < {MIN_RETENTION_DAYS} days, updating")
                                needs_update = True
                            else:
                                log.debug(f"Bucket {bucket}: Current retention {current_days} days >= {MIN_RETENTION_DAYS} days, skipping")
                                results["buckets_skipped"] += 1

                            if needs_update:
                                mc.configure_bucket_lifecycle(bucket=bucket, days=MIN_RETENTION_DAYS)
                                results["buckets_updated"] += 1
                                log.info(f"Bucket {bucket}: Updated retention to {MIN_RETENTION_DAYS} days")

                        except Exception as e:
                            error_msg = f"Error processing bucket {bucket} in project {project_id}: {str(e)}"
                            log.error(error_msg, exc_info=True)
                            results["errors"].append(error_msg)

                except Exception as e:
                    error_msg = f"Error processing project {project_id} ({project_name}): {str(e)}"
                    log.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)

            log.info(
                f"Artifact buckets migration complete: "
                f"{results['projects_processed']} projects, "
                f"{results['buckets_updated']} buckets updated, "
                f"{results['buckets_skipped']} buckets skipped, "
                f"{results['files_touched']} files touched"
            )

            if results["success"]:
                log.info("Migration marked as completed in plugin state")

            return results

        except Exception as e:
            error_msg = f"Critical error during migration: {str(e)}"
            log.error(error_msg, exc_info=True)
            results["success"] = False
            results["errors"].append(error_msg)
            return results

