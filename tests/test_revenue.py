import os
import sqlite3
import hashlib
import json
import secrets
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import assistant, business, revenue
from backend.app import Handler
import test_flows as flow_fixtures


class RevenueTests(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(':memory:',isolation_level=None)
        self.con.row_factory=sqlite3.Row
        self.con.execute('PRAGMA foreign_keys=ON')
        self.con.executescript((Path(__file__).parents[1]/'backend/schema.sql').read_text())
        business.migrate(self.con)
        self.user=self.account('buyer')

    def tearDown(self):
        self.con.close()

    def account(self,uid,created=None):
        self.con.execute('INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)',(uid,uid+'@test.invalid','unused','Test',created or revenue.now(),revenue.now()))
        return self.con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()

    def purchase(self,user,key='checkout_key_123456',test=False,plan='pro_month'):
        intent=revenue.prepare_intent(self.con,user,key,plan,'ai_limit',test)
        remote={'id':'provider-'+key,'amount':{'value':f"{intent['amount_kopecks']/100:.2f}",'currency':'RUB'},'metadata':{'user_id':user['id'],'plan':plan},'test':test,'recipient':{'account_id':'test-shop'},'confirmation':{'confirmation_url':'https://example.test/pay'},'status':'succeeded','paid':True}
        local,created=revenue.persist_checkout(self.con,user,key,plan,intent,remote)
        self.assertTrue(created)
        env={'YOOKASSA_MODE':'test' if test else 'live','YOOKASSA_MERCHANT_TYPE':'self_employed','YOOKASSA_SHOP_ID':'test-shop','YOOKASSA_SECRET_KEY':'fake-test-key'}
        with patch.dict(os.environ,env),patch('backend.mytracker.track_custom_event',return_value=True):
            handler=object.__new__(Handler)
            handler.apply_payment(self.con,local,remote)
            handler.apply_payment(self.con,local,remote)
        return local,remote

    def test_subscription_purchase_gifts_are_issued_once_spent_and_revoked_on_refund(self):
        key='monthly_bonus_checkout'
        local,remote=self.purchase(self.user,key=key,plan='pro_month')
        grant=self.con.execute('SELECT * FROM assistant_bonus_grants WHERE payment_id=?',(local['id'],)).fetchone()
        self.assertIsNotNone(grant)
        self.assertEqual((grant['amount'],grant['remaining']),(50,50))
        self.assertEqual(self.con.execute('SELECT count(*) FROM assistant_bonus_grants WHERE payment_id=?',(local['id'],)).fetchone()[0],1,'duplicate payment confirmation cannot duplicate the bonus')

        service=SimpleNamespace(con=self.con,user=self.con.execute('SELECT * FROM users WHERE id=?',(self.user['id'],)).fetchone())
        quota_key=assistant.quota(service)['key']
        self.con.execute('INSERT INTO rate_limits(key,count,started) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count',(quota_key,100,revenue.now()))
        before=assistant.quota(service)
        self.assertEqual(before['purchase_bonus_remaining'],50)
        self.assertEqual(before['remaining'],50)
        reservation=assistant.reserve(service)
        self.assertEqual(reservation['bonus_grant_id'],grant['id'])
        spent=assistant.quota(service)
        self.assertEqual(spent['purchase_bonus_remaining'],49)
        self.assertEqual(spent['remaining'],49)
        assistant.release(service,reservation)
        restored=assistant.quota(service)
        self.assertEqual(restored['purchase_bonus_remaining'],50,'failed assistant requests return the reserved bonus credit')
        self.assertEqual(restored['remaining'],50)

        # A later request spends exactly one gift credit. A full refund removes only the unused balance.
        reservation=assistant.reserve(service)
        self.assertEqual(reservation['bonus_grant_id'],grant['id'])
        used=assistant.quota(service)
        self.assertEqual(used['purchase_bonus_remaining'],49)
        handler=object.__new__(Handler)
        handler.apply_refund(self.con,{'id':'refund-'+key,'payment_id':remote['id'],'status':'succeeded','amount':remote['amount']})
        revoked=self.con.execute('SELECT remaining FROM assistant_bonus_grants WHERE payment_id=?',(local['id'],)).fetchone()
        self.assertEqual(revoked['remaining'],0)
        self.assertEqual(assistant.quota(service)['remaining'],0,'unused purchase credits are revoked on a full refund')

        annual=self.account('annual-bonus')
        annual_payment,_=self.purchase(annual,key='annual_bonus_checkout',plan='pro_year')
        annual_gift=self.con.execute('SELECT amount,remaining FROM assistant_bonus_grants WHERE payment_id=?',(annual_payment['id'],)).fetchone()
        self.assertEqual((annual_gift['amount'],annual_gift['remaining']),(300,300))

        tester=self.account('test-bonus')
        test_payment,_=self.purchase(tester,key='test_bonus_checkout',test=True,plan='pro_year')
        self.assertIsNone(self.con.execute('SELECT id FROM assistant_bonus_grants WHERE payment_id=?',(test_payment['id'],)).fetchone(),'test checkouts do not mint purchase bonuses')

    def test_four_tier_catalog_has_monthly_and_annual_checkout_products(self):
        offer = revenue.pricing(self.con, self.user)
        catalog = {item["id"]: item for item in offer["catalog"]}
        self.assertEqual(set(catalog), {"pro_solo", "pro_plus", "team_company", "business_partner"})
        expected = {
            "pro_month": 49000,
            "pro_year": 490000,
            "pro_plus_month": 69000,
            "pro_plus_year": 690000,
            "team_month": 399000,
            "team_year": 3990000,
            "business_month": 999000,
            "business_year": 9990000,
        }
        self.assertEqual({key: value["amount_kopecks"] for key, value in offer["plans"].items()}, expected)
        for item in catalog.values():
            self.assertIn(item["plan"], offer["plans"])
            self.assertIn(item["annual_plan"], offer["plans"])
            self.assertLess(offer["plans"][item["annual_plan"]]["amount_kopecks"],
                            offer["plans"][item["plan"]]["amount_kopecks"] * 12)
        self.assertEqual(catalog["team_company"]["seat_limit"], 5)
        self.assertEqual(catalog["business_partner"]["seat_limit"], 15)
        self.assertEqual(offer["limits"]["pro_quotes"], 10000)

    def test_confirmed_paid_product_sets_workspace_tier_and_test_flag(self):
        cases = [
            ("solo-live", "pro_month", "pro_solo", 1, False),
            ("plus-live", "pro_plus_month", "pro_plus", 1, False),
            ("team-live", "team_month", "team", 5, False),
            ("business-live", "business_year", "business", 15, False),
            ("team-test", "team_month", "free", 1, True),
        ]
        for uid, plan, expected_tier, expected_seats, test_mode in cases:
            user = self.account(uid)
            local, _ = self.purchase(user, key="checkout_"+uid, plan=plan, test=test_mode)
            workspace = self.con.execute(
                "SELECT * FROM workspaces WHERE owner_id=?", (uid,)
            ).fetchone()
            self.assertIsNotNone(workspace)
            self.assertEqual(workspace["plan"], expected_tier)
            self.assertEqual(workspace["seat_limit"], expected_seats)
            subscription = self.con.execute(
                "SELECT product_code,is_test,status,current_period_end FROM billing_subscriptions "
                "WHERE provider_subscription_id=?", (local["provider_id"],)
            ).fetchone()
            self.assertIsNotNone(subscription)
            self.assertEqual(subscription["product_code"], plan)
            self.assertEqual(bool(subscription["is_test"]), test_mode)
            self.assertEqual(subscription["status"], "active")
            self.assertGreater(subscription["current_period_end"], revenue.now())

    def test_price_assignment_and_retry_preserve_original_terms(self):
        config={'PRICING_EXPERIMENT_ID':'launch-test','PRICING_VARIANTS_JSON':'{"a":{"month":29900,"year":239000},"b":{"month":49900,"year":399000}}'}
        with patch.dict(os.environ,config):
            first=revenue.pricing(self.con,self.user)
            self.assertEqual(first,revenue.pricing(self.con,self.user))
            intent=revenue.prepare_intent(self.con,self.user,'durable_checkout_key','pro_month','ai_limit',False)
        with patch.dict(os.environ,{'PRO_MONTH_PRICE_KOPECKS':'69900','PRO_YEAR_PRICE_KOPECKS':'559000'}):
            retry=revenue.prepare_intent(self.con,self.user,'durable_checkout_key','pro_month','settings',False)
        self.assertEqual(retry['amount_kopecks'],intent['amount_kopecks'])
        self.assertEqual(retry['source'],'ai_limit')
        with self.assertRaises(ValueError):
            revenue.prepare_intent(self.con,self.user,'durable_checkout_key','pro_year','settings',False)
        with self.assertRaises(ValueError):
            revenue.prepare_intent(self.con,self.user,'durable_checkout_key','pro_month','settings',True)

    def test_displayed_price_is_checked_before_creating_payment_intent(self):
        with self.assertRaises(ValueError):
            revenue.prepare_intent(self.con,self.user,'mismatch_price_key','pro_month','pricing_page',False,49900)
        self.assertEqual(self.con.execute('SELECT count(*) FROM billing_intents').fetchone()[0],0)
        intent=revenue.prepare_intent(self.con,self.user,'matching_price_key','pro_month','pricing_page',False,49000)
        with patch.dict(os.environ,{'PRO_MONTH_PRICE_KOPECKS':'59900','PRO_YEAR_PRICE_KOPECKS':'599000'}):
            self.assertEqual(revenue.prepare_intent(self.con,self.user,'matching_price_key','pro_month','pricing_page',False,49000)['id'],intent['id'])
        with self.assertRaises(ValueError):
            revenue.prepare_intent(self.con,self.user,'matching_price_key','pro_month','pricing_page',False,59900)

    def test_test_payments_manual_access_and_refunds_are_not_revenue(self):
        local,_=self.purchase(self.user)
        self.purchase(self.account('tester'),key='test_checkout_1234',test=True)
        manual=self.account('manual')
        self.con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE id=?",(revenue.now()+86400,manual['id']))
        data=revenue.dashboard(self.con)
        self.assertEqual(data['revenue_30d'],49000)
        self.assertEqual(data['paid_users'],1)
        self.assertEqual(data['funnel']['payment_success'],1)
        self.assertEqual(data['funnel']['subscription_started'],1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM growth_events WHERE name='payment_success'").fetchone()[0],1)
        self.con.execute('INSERT INTO refunds(id,payment_id,provider_id,amount_kopecks,status,created_at) VALUES(?,?,?,?,?,?)',('refund',local['id'],'refund-provider',49000,'succeeded',revenue.now()))
        self.assertEqual(revenue.dashboard(self.con)['revenue_30d'],0)
        self.assertEqual(revenue.dashboard(self.con)['mrr_kopecks'],0)

    def test_activation_referral_rewards_are_once_only_and_capped(self):
        code=revenue.referral(self.con,self.user)['code']
        friend=self.account('friend')
        revenue.referral(self.con,friend,code)
        self.assertEqual(revenue.referral(self.con,self.user)['bonus'],0)
        revenue.activate(self.con,friend['id'],'estimate_created','quote-id')
        revenue.activate(self.con,friend['id'],'estimate_shared','quote-id')
        self.assertEqual(revenue.referral(self.con,self.user)['bonus'],3)
        self.assertEqual(self.con.execute("SELECT count(*) FROM growth_events WHERE name='activated' AND user_id=?",(friend['id'],)).fetchone()[0],1)
        old=self.account('old',revenue.now()-2*86400)
        revenue.referral(self.con,old,code)
        self.assertIsNone(self.con.execute('SELECT * FROM referral_rewards WHERE invitee_id=?',(old['id'],)).fetchone())
        for index in range(11):
            extra=self.account('friend-'+str(index))
            revenue.referral(self.con,extra,code)
            revenue.activate(self.con,extra['id'],'estimate_created','quote-extra-'+str(index))
        self.assertEqual(revenue.referral_bonus(self.con,self.user['id'],__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m')),30)

    def test_mature_cohorts_unknown_costs_and_conversion_denominators(self):
        old=self.account('retained',revenue.now()-8*86400)
        day=old['created_at']//86400
        revenue.record(self.con,old['id'],'product_visit',key='retention-d7')
        self.con.execute('UPDATE growth_events SET created_at=? WHERE dedupe_key=?',((day+7)*86400+100,'retention-d7'))
        report=revenue.dashboard(self.con)
        self.assertEqual(next(c for c in report['cohorts'] if c['day']==7)['retained'],1)
        self.assertIsNone(next(c for c in report['cohorts'] if c['day']==30)['retention_pct'])
        self.assertIsNone(report['ltv_kopecks'])
        self.assertFalse(report['economics']['costs_configured'])
        self.assertIsNone(report['paywall_conversion_pct'])
        self.assertTrue(all(0<=c['activation_d0']<=c['signups'] for c in report['signup_cohorts']))


class RevenueApiTests(unittest.TestCase):
    setUpClass=classmethod(flow_fixtures.FlowTests.setUpClass.__func__)
    tearDownClass=classmethod(flow_fixtures.FlowTests.tearDownClass.__func__)
    request=flow_fixtures.FlowTests.request

    def account(self,admin=False):
        token,uid=secrets.token_urlsafe(32),secrets.token_hex(16)
        with self.mod.db() as con:
            con.execute('INSERT INTO users(id,email,password_hash,name,role,created_at,email_verified_at) VALUES(?,?,?,?,?,?,?)',(uid,uid+'@test.invalid','unused','Revenue','admin' if admin else 'user',revenue.now(),revenue.now()))
            con.execute('INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)',(secrets.token_hex(16),uid,hashlib.sha256(token.encode()).hexdigest(),revenue.now()+3600))
        return token,uid

    def test_checkout_rejects_changed_or_invalid_displayed_price_before_provider(self):
        token,_=self.account()
        def checkout(amount,key):
            request=urllib.request.Request(self.base+'/api/billing/checkout',json.dumps({'plan':'pro_month','expected_amount_kopecks':amount}).encode(),{'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':key},method='POST')
            try:
                with urllib.request.urlopen(request,timeout=5) as response:
                    return response.code,json.load(response)
            except urllib.error.HTTPError as error:
                return error.code,json.load(error)
        with patch.dict(os.environ,{'YOOKASSA_MODE':'live','YOOKASSA_SHOP_ID':'isolated-shop','YOOKASSA_SECRET_KEY':'live_isolated_test','YOOKASSA_MERCHANT_TYPE':'self_employed','PRO_MONTH_PRICE_KOPECKS':'49000','PRO_YEAR_PRICE_KOPECKS':'490000'}),patch.object(self.mod.Handler,'provider_call') as provider:
            self.assertEqual(checkout(59900,'changed-price-checkout-key')[0],409)
            self.assertEqual(checkout(True,'invalid-price-checkout-key')[0],400)
            provider.assert_not_called()

    def test_public_price_and_private_revenue_cannot_be_forged(self):
        token,uid=self.account()
        self.assertEqual(self.request('/api/admin/revenue',token=token)[0],403)
        self.assertEqual(self.request('/api/admin/revenue')[0],401)
        self.assertEqual(self.request('/api/billing/events','POST',{'name':'payment_success','source':'ai_limit'},token)[0],400)
        self.assertEqual(self.request('/api/billing/events','POST',{'name':'paywall_viewed','source':'ai_limit','user_id':'somebody-else','variant':'invented'},token)[0],200)
        with self.mod.db() as con:
            row=con.execute("SELECT * FROM growth_events WHERE user_id=? AND name='paywall_viewed'",(uid,)).fetchone()
            self.assertEqual(row['variant'],'baseline:baseline')
        self.assertEqual(self.request('/api/billing/pricing')[0],200)
        status,data=self.request('/api/admin/revenue',token=self.account(True)[0])
        self.assertEqual(status,200)
        self.assertEqual(data['recurring'],False)
        self.assertIn('first_estimate',data)

    def test_first_quote_activation_share_approval_and_branding(self):
        token,uid=self.account()
        status,created=self.request('/api/quotes','POST',{'title':'Repair','client':'Client','items':[{'name':'Work','quantity':'1','unit':'job','unit_price':10000}]},token)
        self.assertEqual(status,201)
        quote=created['quote']
        self.assertEqual(self.request('/api/quotes/'+quote['id']+'/publish','POST',{'revision':quote['revision']},token)[0],200)
        public_token=quote['public_url'].split('quote=')[1]
        self.assertEqual(self.request('/api/public/respond','POST',{'token':public_token,'version':1,'name':'Client','action':'approved'})[0],200)
        with self.mod.db() as con:
            names={r[0] for r in con.execute('SELECT name FROM growth_events WHERE user_id=?',(uid,))}
        self.assertTrue({'activated','estimate_created','estimate_shared','estimate_approved'}<=names)
        self.assertEqual(self.request('/api/workspace','PATCH',{'settings':{'hide_branding':True}},token)[0],402)
        with self.mod.db() as con:
            con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE id=?",(revenue.now()+86400,uid))
        self.assertEqual(self.request('/api/workspace','PATCH',{'settings':{'hide_branding':True}},token)[0],200)
        status,page=self.request('/api/public/quote?token='+public_token)
        self.assertEqual(status,200)
        self.assertFalse(page['show_branding'])


if __name__=='__main__':
    unittest.main()
