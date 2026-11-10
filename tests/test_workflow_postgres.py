"""Run the same commercial API scenarios through PostgreSQL's real runtime role."""
import os
import hashlib
import sqlite3
import unittest

from tests import test_estimate_workflow as workflow, test_estimate_assemblies as assemblies
from tests import test_protected_changes as changes, test_protected_estimates as protected


class PostgresEnvironment:
    setUpClass = classmethod(protected.ProtectedEstimatePostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(protected.ProtectedEstimatePostgresTests.tearDownClass.__func__)

    def setUp(self):
        with self.mod.db() as con:
            con.execute("DELETE FROM rate_limits")
        super().setUp()

    def tearDown(self):
        with self.mod.db() as con:
            wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=? AND role='owner'", (self.owner_id if hasattr(self, "owner_id") else self.uid,)).fetchone()[0]
            con.execute("DELETE FROM construction_objects WHERE workspace_id=?", (wid,))
            con.execute("DELETE FROM projects WHERE workspace_id=?", (wid,))
            con.execute("DELETE FROM quotes WHERE workspace_id=?", (wid,))
            con.execute("DELETE FROM workspaces WHERE id=?", (wid,))


enabled = unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"), "requires disposable PostgreSQL schema 73")


@enabled
class WorkflowPostgresTests(PostgresEnvironment, workflow.WorkflowTests):
    def test_payment_eligibility_helper_is_scoped_and_exposes_no_payment_rows(self):
        from backend.postgres import Connection
        with self.mod.db() as con:
            wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=? AND role='owner'", (self.uid,)).fetchone()[0]
            self.assertFalse(con.execute("SELECT has_function_privilege('anon','smetra.runtime_workspace_has_bound_payment(text)','EXECUTE')").fetchone()[0])
        runtime = Connection(runtime=True)
        try:
            runtime.scope(hashlib.sha256(self.owner.encode()).hexdigest(), wid)
            self.assertFalse(runtime.execute("SELECT smetra.runtime_workspace_has_bound_payment(?)", (wid,)).fetchone()[0])
            self.assertTrue(runtime.execute("SELECT smetra.runtime_workspace_has_bound_payment(?)", ("unrelated-workspace",)).fetchone()[0])
            self.assertFalse(runtime.execute("SELECT has_table_privilege(current_user,'smetra.payments','SELECT')").fetchone()[0])
        finally:
            runtime.finish(False)

    def test_database_prevents_two_accepted_options_even_outside_api(self):
        quotes = self.alternatives()
        with self.mod.db() as con:
            con.execute("UPDATE quotes SET approval_state='approved' WHERE id=?", (quotes[0]["id"],))
        with self.assertRaises(sqlite3.IntegrityError), self.mod.db() as con:
            con.execute("UPDATE quotes SET approval_state='approved' WHERE id=?", (quotes[1]["id"],))


@enabled
class AssemblyPostgresTests(PostgresEnvironment, assemblies.AssemblyFlows):
    pass


@enabled
class ProtectedChangePostgresTests(PostgresEnvironment, changes.ProtectedChangeTests):
    pass
