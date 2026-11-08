"""Account statistics use scoped records, exact recorded cash and private token history."""
import datetime as dt
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_business


class ProfileSummaryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_summary_keeps_currencies_separate_and_does_not_multiply_transactions(self):
        owner, _ = self.account('summary-owner')
        other, _ = self.account('summary-other')
        project = self.call('/projects', 'POST', {'name': 'Заказ', 'amount_kopecks': 100000}, owner)[1]['item']
        foreign = self.call('/projects', 'POST', {'name': 'Чужой заказ', 'amount_kopecks': 900000}, other)[1]['item']
        today = dt.date(2026, 11, 8)
        with patch('backend.business.business_date', return_value=today), patch('backend.profile_summary.business_date', return_value=today):
            for token, pid, value, date in [(owner, project['id'], 1500, '2026-11-01'), (owner, project['id'], 2500, '2026-10-01'), (owner, project['id'], 5000, '2026-11-20'), (other, foreign['id'], 90000, '2026-11-01')]:
                self.assertEqual(self.call('/receipts', 'POST', {'project_id': pid, 'amount_kopecks': value, 'payment_date': date}, token, key=str(uuid.uuid4()))[0], 201)
            for value in (300, 700):
                self.assertEqual(self.call('/expenses', 'POST', {'project_id': project['id'], 'amount_kopecks': value, 'category': 'Материалы', 'expense_date': '2026-11-02'}, owner, key=str(uuid.uuid4()))[0], 201)
            with self.mod.db() as con:
                con.execute("UPDATE projects SET status='cancelled' WHERE id=?", (project['id'],))
            code, result = self.call('/profile-summary', token=owner)
            self.assertEqual(code, 200, result)
            cash = result['money']['currencies'][0]
            self.assertEqual((cash['received'], cash['spent'], cash['balance']), (4000, 1000, 3000))
            self.assertEqual((cash['received_month'], cash['spent_month']), (1500, 1000))
            self.assertEqual([m['month'] for m in cash['months']], ['2026-06', '2026-07', '2026-08', '2026-09', '2026-10', '2026-11'])
            self.assertEqual(result['counts']['active_projects'], 0)
            self.assertNotIn('Чужой заказ', str(result))
        self.assertEqual(self.call('/profile-summary')[0], 401)
        self.assertEqual(self.call('/profile-summary', 'POST', {}, owner)[0], 405)

    def test_completed_estimates_have_their_own_status_in_the_profile(self):
        token, _ = self.account('summary-completed')
        code, result = self.call('/quotes', 'POST', {'title': 'Работы', 'client': 'Клиент', 'items': [{'name': 'Работа', 'quantity': '1', 'unit_price': 100}]}, token)
        self.assertEqual(code, 201, result)
        with self.mod.db() as con:
            con.execute("UPDATE quotes SET status='completed',approval_state='approved' WHERE id=?", (result['quote']['id'],))
        code, result = self.call('/profile-summary', token=token)
        self.assertEqual(code, 200, result)
        self.assertEqual(result['quote_states'], {'completed': 1})

    def test_finance_is_hidden_for_members_without_finance_permission(self):
        owner, _ = self.account('summary-finance-owner')
        viewer, viewer_id = self.account('summary-finance-viewer')
        outsider, _ = self.account('summary-finance-outsider')
        workspace = self.call('/workspace', token=owner)[1]['workspace']['id']
        with self.mod.db() as con:
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'viewer')", (workspace, viewer_id))
        code, result = self.call('/profile-summary', token=viewer, workspace=workspace)
        self.assertEqual(code, 200, result)
        self.assertIsNone(result['money'])
        self.assertEqual(self.call('/profile-summary', token=outsider, workspace=workspace)[0], 404)

    def test_usage_does_not_require_restricted_users_created_at_permission(self):
        token, user_id = self.account('usage-runtime-owner')
        self.call('/workspace', token=token)
        from backend.usage import summary
        with self.mod.db() as con:
            wid = con.execute('SELECT id FROM workspaces WHERE owner_id=?', (user_id,)).fetchone()[0]
            user = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()

            class Restricted:
                def execute(self, sql, params=()):
                    if 'users' in sql.lower() and 'created_at' in sql.lower():
                        raise PermissionError('Runtime role cannot read registration metadata')
                    return con.execute(sql, params)

            service = SimpleNamespace(con=Restricted(), global_con=con, wid=wid, user=user)
            code, result = summary(service)
            self.assertEqual(code, 200)
            self.assertEqual(result['quotes']['used'], 0)
            self.assertGreater(result['tokens']['limit'], 0)

    def test_quote_creation_and_limit_work_with_restricted_user_columns(self):
        token, _ = self.account('runtime-quote-owner', legacy=False)
        from backend.business import Service
        original = Service.create_quote

        class Restricted:
            def __init__(self, con):
                self.con = con

            def __getattr__(self, name):
                return getattr(self.con, name)

            def execute(self, sql, params=()):
                if 'users' in sql.lower() and 'created_at' in sql.lower():
                    raise PermissionError('Runtime role cannot read registration metadata')
                return self.con.execute(sql, params)

        def guarded(service, data):
            previous = service.con
            service.con = Restricted(previous)
            try:
                return original(service, data)
            finally:
                service.con = previous

        with patch.object(Service, 'create_quote', guarded):
            for index in range(4):
                code, result = self.call('/quotes', 'POST', {'title': 'Проверка '+str(index), 'client': 'Демо', 'items': [{'name': 'Работа', 'quantity': '1', 'unit_price': 100}]}, token)
                self.assertEqual(code, 201 if index < 3 else 402, result)

    def test_usage_history_is_personal_and_bounded(self):
        owner, owner_id = self.account('usage-ledger-owner')
        _, other_id = self.account('usage-ledger-other')
        from backend.ai_tokens import credit
        with self.mod.db() as con:
            credit(con, owner_id, 3500, 'token_pack')
            credit(con, other_id, 99000, 'admin_adjust')
        code, result = self.call('/usage', token=owner)
        self.assertEqual(code, 200, result)
        self.assertEqual(result['history']['added'], 3500)
        self.assertEqual(result['history']['entries'][0]['delta'], 3500)
        self.assertNotIn(other_id, str(result['history']))
        self.assertEqual(result['history']['spent'], 0)
