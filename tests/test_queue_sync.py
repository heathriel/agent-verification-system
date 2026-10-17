"""Regression tests shared by both queue-sync entry points."""

import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ArtifactSelectionTests:
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "queue_sync_under_test", ROOT / "lib" / self.script_name
        )
        self.sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sync)
        self.temp = tempfile.TemporaryDirectory(prefix="avs_queue_sync_")
        self.addCleanup(self.temp.cleanup)
        self.artifact_dir = Path(self.temp.name) / "completion_artifacts"
        self.artifact_dir.mkdir()
        self.sync.ARTIFACT_DIR = str(self.artifact_dir)
        self.sync.AVS_ARTIFACT_DIR = str(self.artifact_dir)
        self.sync.QUEUE_FILE = str(Path(self.temp.name) / "queue.yaml")
        self.task_id = "build_report"

    def write_artifact(self, timestamp, status, *, suffix="", **fields):
        path = self.artifact_dir / f"TASK_{self.task_id}{suffix}_{timestamp}.yaml"
        artifact = {
            "task_id": self.task_id,
            "status": status,
            "timestamp_end": timestamp,
            "outputs": [],
            **fields,
        }
        path.write_text(yaml.safe_dump(artifact))
        return str(path)

    def assert_latest_status(self, older, newer, expected_status):
        # glob order is unspecified: the result must be correct in either order.
        for paths in ([older, newer], [newer, older]):
            with self.subTest(paths=paths):
                task = {"id": self.task_id, "status": "in_progress"}
                with patch.object(self.sync, "find_artifacts_for_task", return_value=paths):
                    changed, _ = self.sync.sync_task_status(task)
                self.assertTrue(changed)
                self.assertEqual(task["status"], expected_status)

    def test_new_failure_does_not_reuse_old_success(self):
        older = self.write_artifact("20260205_143000", "complete")
        newer = self.write_artifact("20260205_153000", "failed")
        self.assert_latest_status(older, newer, "failed")

    def test_new_success_does_not_reuse_old_failure(self):
        older = self.write_artifact("20260205_143000", "failed")
        newer = self.write_artifact("20260205_153000", "complete")
        self.assert_latest_status(older, newer, "complete")

    def test_date_is_compared_before_time_of_day(self):
        older = self.write_artifact("20261231_235959", "complete")
        newer = self.write_artifact("20270101_000001", "failed")
        self.assert_latest_status(older, newer, "failed")

    def test_theater_suffix_keeps_full_timestamp(self):
        older = self.write_artifact("20260205_143000", "complete")
        newer = self.write_artifact("20260205_153000", "failed", suffix="_theater")
        self.assert_latest_status(older, newer, "failed")

    def test_malformed_filename_does_not_override_dated_artifact(self):
        older = self.write_artifact("invalid_timestamp", "complete")
        newer = self.write_artifact("20260205_153000", "failed")
        self.assert_latest_status(older, newer, "failed")

    def test_invalid_newest_artifact_blocks_instead_of_reusing_success(self):
        older = self.write_artifact("20260205_143000", "complete")
        newer = self.write_artifact("20260205_153000", "complete")
        Path(newer).write_text("task_id: build_report\n")
        self.assert_latest_status(older, newer, "blocked")

    def test_partial_artifact_preserves_in_progress_and_updates_notes(self):
        older = self.write_artifact("20260205_143000", "complete")
        newer = self.write_artifact(
            "20260205_153000", "partial", next_steps_if_partial="Finish review"
        )
        task = {"id": self.task_id, "status": "in_progress"}
        with patch.object(self.sync, "find_artifacts_for_task", return_value=[older, newer]):
            changed, _ = self.sync.sync_task_status(task)
        self.assertTrue(changed)
        self.assertEqual(task["status"], "in_progress")
        self.assertEqual(task["notes"], "Partial complete. Next: Finish review")

    def test_single_artifact_still_syncs(self):
        self.write_artifact("20260205_153000", "complete")
        task = {"id": self.task_id, "status": "in_progress"}
        changed, _ = self.sync.sync_task_status(task)
        self.assertTrue(changed)
        self.assertEqual(task["status"], "complete")
        self.assertEqual(task["completed_at"], "20260205_153000")

    def test_main_persists_latest_artifact_status(self):
        older = self.write_artifact("20260205_143000", "complete")
        newer = self.write_artifact(
            "20260205_153000", "failed", failure_mode="Review failed"
        )
        queue = {"tasks": [{"id": self.task_id, "status": "in_progress"}]}
        Path(self.sync.QUEUE_FILE).write_text(yaml.safe_dump(queue))
        with patch.object(self.sync, "find_artifacts_for_task", return_value=[older, newer]):
            with contextlib.redirect_stdout(io.StringIO()):
                result = self.sync.main()
        self.assertEqual(result, 0)
        saved_task = yaml.safe_load(Path(self.sync.QUEUE_FILE).read_text())["tasks"][0]
        self.assertEqual(saved_task["status"], "failed")
        self.assertEqual(saved_task["failure_mode"], "Review failed")
        self.assertNotIn("completed_at", saved_task)


class QueueSyncArtifactsTests(ArtifactSelectionTests, unittest.TestCase):
    script_name = "queue-sync-artifacts.py"


class QueueSyncTests(ArtifactSelectionTests, unittest.TestCase):
    script_name = "queue-sync.py"


if __name__ == "__main__":
    unittest.main()
