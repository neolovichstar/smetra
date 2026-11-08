"""Real HTTP boundary: public counters are anonymous, reports are admin-only."""
import hashlib
import json
import secrets
import urllib.error
import urllib.request
import unittest
import uuid

from tests import test_flows


class SiteTrafficApiTests(unittest.TestCase):
    setUpClass = classmethod(test_flows.FlowTests.setUpClass.__func__)
    tearDownClass = classmethod(test_flows.FlowTests.tearDownClass.__func__)

    def request(self, path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def make_session(self, admin=False):
        token, user_id = secrets.token_urlsafe(32), self.mod.uid()
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) "
                "VALUES(?,?,?,'Visitor QA',?,?)",
                (user_id, user_id+'@test.invalid', 'unused', self.mod.now(), self.mod.now()),
            )
            if admin:
                con.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
            con.execute(
                "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                (self.mod.uid(), user_id, hashlib.sha256(token.encode()).hexdigest(), self.mod.now()+3600),
            )
        return token

    def test_public_visit_is_logged_without_auth_and_admin_report_is_private(self):
        visitor = str(uuid.uuid4())
        self.assertEqual(self.request('/api/public/visit', {'visitor_id':visitor,'page':'landing'})[0],200)
        self.assertEqual(self.request('/api/public/visit', {'visitor_id':visitor,'page':'landing'})[0],200)
        self.assertEqual(self.request('/api/admin/traffic')[0],401)
        self.assertEqual(self.request('/api/admin/traffic',token=self.make_session())[0],403)
        code, report = self.request('/api/admin/traffic',token=self.make_session(admin=True))
        self.assertEqual(code,200,report)
        self.assertGreaterEqual(report['today'],1)
        self.assertGreaterEqual(report['views_30d'],2)
        self.assertEqual(len(report['daily']),30)
        self.assertNotIn(visitor,json.dumps(report))
        with self.mod.db() as con:
            self.assertNotIn(visitor,str([dict(x) for x in con.execute('SELECT * FROM site_visits')]))

    def test_invalid_site_visit_does_not_write(self):
        code, _ = self.request('/api/public/visit', {'visitor_id':'not-a-uuid','page':'landing'})
        self.assertEqual(code,400)
        code, _ = self.request('/api/public/visit', {'visitor_id':str(uuid.uuid4()),'page':'admin'})
        self.assertEqual(code,400)


if __name__ == '__main__':
    unittest.main()
