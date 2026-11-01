"""First-touch marketing attribution: captured once for new accounts, summarised for admins."""
import time
import unittest

from backend import attribution
from tests import test_business


class Attribution(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_new_account_keeps_its_first_touch_and_admins_see_channels(self):
        token, user_id = self.account("utm-new")
        admin, admin_id = self.account("utm-admin")
        old, old_id = self.account("utm-old")
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (admin_id,))
            con.execute("UPDATE users SET created_at=? WHERE id=?", (int(time.time()) - 40 * 86400, old_id))
        first = {"source": "Yandex", "medium": "cpc", "campaign": "plitka_msk", "referrer": "www.yandex.ru",
                 "landing": "/", "first_seen_at": int(time.time()) - 3600, "at": 1}
        status, body = self.call("/me/attribution", "POST", first, token)
        self.assertEqual((status, body["saved"]), (200, True))
        # The first touch stays; a later campaign does not overwrite it.
        self.assertFalse(self.call("/me/attribution", "POST", {"source": "vk", "medium": "social"}, token)[1]["saved"])
        # Old customers are never attributed to a campaign they clicked later.
        self.assertFalse(self.call("/me/attribution", "POST", first, old)[1]["saved"])
        # Nothing usable: no tags and no valid referring host.
        self.assertFalse(self.call("/me/attribution", "POST", {"source": "<script>", "referrer": "javascript:alert(1)"}, admin)[1]["saved"])
        self.assertEqual(self.call("/me/attribution", "POST", ["x"], admin)[0], 400)
        with self.mod.db() as con:
            row = dict(con.execute("SELECT source,medium,campaign,referrer_host,landing_path FROM user_attribution WHERE user_id=?",
                                   (user_id,)).fetchone())
        self.assertEqual(row, {"source": "yandex", "medium": "cpc", "campaign": "plitka_msk",
                               "referrer_host": "yandex.ru", "landing_path": "/"})

        self.assertEqual(self.call("/admin/revenue", token=token)[0], 403)
        status, revenue = self.call("/admin/revenue", token=admin)
        self.assertEqual(status, 200)
        channels = {item["channel"]: item for item in revenue["acquisition"]["items"]}
        self.assertEqual((channels["yandex / cpc"]["campaign"], channels["yandex / cpc"]["signups"]), ("plitka_msk", 1))
        self.assertIn("прямые и без меток", channels)

    def test_channel_names(self):
        self.assertEqual(attribution.channel("", "", "yandex.ru"), "поиск: yandex.ru")
        self.assertEqual(attribution.channel("", "", "m.vk.com"), "соцсети: m.vk.com")
        self.assertEqual(attribution.channel("", "", "forumhouse.ru"), "сайт: forumhouse.ru")
        self.assertEqual(attribution.channel("telegram", "post", ""), "telegram / post")


if __name__ == "__main__":
    unittest.main()
