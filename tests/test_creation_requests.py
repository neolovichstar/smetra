"""Creation retries must not duplicate files or conversations after a lost response."""

import base64
import concurrent.futures
import unittest

import test_business


class CreationRequestTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def file_body(self):
        return {"assistant_upload": True, "name": "brief.md",
                "content": base64.b64encode(b"# Paint walls").decode()}

    def test_parallel_uploads_replay_once_and_changed_payload_conflicts(self):
        owner, user_id = self.account("upload-parallel")
        body = self.file_body()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(self.call, "/files", "POST", body, owner, key="retry-file") for _ in range(2)]
            responses = [request.result() for request in requests]
        self.assertEqual(sorted(status for status, _ in responses), [200, 201], responses)
        ids = [result["file"]["id"] for _, result in responses]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(self.call("/files", "POST", {**body, "name": "changed.md"}, owner, key="retry-file")[0], 409)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM files WHERE id=?", (ids[0],)).fetchone()[0], 1)
            row = con.execute("SELECT key_hash,request_hash FROM creation_requests WHERE user_id=?", (user_id,)).fetchone()
            self.assertEqual(len(row["key_hash"]), 64)
            self.assertEqual(len(row["request_hash"]), 64)

    def test_upload_keys_are_private_and_deleted_results_are_not_recreated(self):
        owner, _ = self.account("upload-private-owner")
        other, _ = self.account("upload-private-other")
        body = self.file_body()
        first = self.call("/files", "POST", body, owner, key="same-key")[1]["file"]
        status, second = self.call("/files", "POST", body, other, key="same-key")
        self.assertEqual(status, 201, second)
        self.assertNotEqual(first["id"], second["file"]["id"])
        self.assertEqual(self.call("/files/"+first["id"], "DELETE", token=owner)[0], 200)
        self.assertEqual(self.call("/files", "POST", body, owner, key="same-key")[0], 409)

    def test_failed_upload_does_not_claim_key(self):
        owner, _ = self.account("upload-invalid")
        body = self.file_body()
        self.assertEqual(self.call("/files", "POST", {**body, "content": "invalid"}, owner, key="validated-key")[0], 400)
        self.assertEqual(self.call("/files", "POST", body, owner, key="validated-key")[0], 201)
        self.assertEqual(self.call("/files", "POST", body, owner, key="x"*101)[0], 400)

    def test_parallel_conversation_creation_and_deleted_tombstone(self):
        owner, _ = self.account("conversation-parallel")
        body = {"title": "Document questions"}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(self.call, "/assistant/conversations", "POST", body, owner, key="retry-thread") for _ in range(2)]
            responses = [request.result() for request in requests]
        self.assertEqual(sorted(status for status, _ in responses), [200, 201], responses)
        thread_id = responses[0][1]["conversation"]["id"]
        self.assertEqual(thread_id, responses[1][1]["conversation"]["id"])
        self.assertEqual(len(self.call("/assistant/conversations", token=owner)[1]["items"]), 1)
        self.assertEqual(self.call("/assistant/conversations", "POST", {"title": "Changed"}, owner, key="retry-thread")[0], 409)
        self.assertEqual(self.call("/assistant/conversations/"+thread_id, "DELETE", token=owner)[0], 200)
        self.assertEqual(self.call("/assistant/conversations", "POST", body, owner, key="retry-thread")[0], 409)

    def test_conversation_replay_at_capacity_and_file_key_namespace(self):
        owner, _ = self.account("conversation-capacity-retry")
        other, _ = self.account("conversation-capacity-other")
        body = {"title": "Document questions"}
        first = self.call("/assistant/conversations", "POST", body, owner, key="shared-operation")[1]["conversation"]
        self.assertEqual(self.call("/files", "POST", self.file_body(), owner, key="shared-operation")[0], 201)
        self.assertEqual(self.call("/assistant/conversations", "POST", body, other, key="shared-operation")[0], 201)
        with self.mod.db() as con:
            for index in range(49):
                con.execute("INSERT INTO assistant_conversations(id,workspace_id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            ("capacity-"+str(index), first["workspace_id"], first["user_id"], "Capacity", 0, 0))
        status, replay = self.call("/assistant/conversations", "POST", body, owner, key="shared-operation")
        self.assertEqual(status, 200, replay)
        self.assertEqual(replay["conversation"]["id"], first["id"])
        self.assertEqual(self.call("/assistant/conversations", "POST", body, owner)[0], 409)
