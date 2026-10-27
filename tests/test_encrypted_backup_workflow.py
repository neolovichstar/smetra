"""Fail closed if automated recovery starts publishing plaintext archives."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-backup.yml"


class EncryptedBackupWorkflowTests(unittest.TestCase):
    def test_scheduled_job_uses_only_explicit_secrets_and_public_recipient(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cron: '37 4 * * *'", content)
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("secrets.SMETRA_BACKUP_DATABASE_URL", content)
        self.assertIn("vars.SMETRA_BACKUP_AGE_RECIPIENT", content)
        self.assertNotIn("secrets.SMETRA_BACKUP_AGE_IDENTITY", content)
        self.assertNotIn("pull_request:", content)
        self.assertIn("persist-credentials: false", content)

    def test_plaintext_dumps_are_not_published_as_artifacts(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        upload = content.split("- name: Upload encrypted archive only", 1)[1]
        self.assertIn("actions/upload-artifact@v4", upload)
        self.assertIn("*.age*", upload)
        self.assertNotIn("*.dump", upload)
        self.assertNotIn("*.json", upload)
        self.assertIn("retention-days: 30", upload)
        self.assertIn("age --encrypt -r", content)
        self.assertIn("pg_restore --list", content)
        self.assertIn('trap cleanup EXIT', content)
        self.assertIn("set -euo pipefail", content)

    def test_backup_uses_reviewed_persistence_tool(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python -m backend.manage backup --schema smetra", content)
        self.assertIn("postgresql-client-17", content)
        self.assertIn("sha256sum", content)


if __name__ == "__main__":
    unittest.main()
