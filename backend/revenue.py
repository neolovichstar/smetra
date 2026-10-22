"""First useful estimate, honest paid conversion and configurable pricing.

Browser events cannot grant entitlement or manufacture confirmed revenue.
No external analytics network calls participate in a work/payment transaction.
"""
import datetime as dt
import hashlib
import json
import os
import secrets
import time
import uuid

try:
    from backend.plan_catalog import PUBLIC_PLANS, PUBLIC_PLAN_CODES
except ModuleNotFoundError:
    from plan_catalog import PUBLIC_PLANS, PUBLIC_PLAN_CODES

SOURCES = frozenset('project_limit quote_limit ai_limit pdf_export file_analysis documents settings pricing_page activation referral other'.split())
CLIENT_EVENTS = frozenset(('paywall_viewed', 'upgrade_clicked'))
# Included assistant bonus credits are issued only after provider-confirmed subscription payments.
PURCHASE_BONUS_MESSAGES = {
    'pro_month': 50,
    'pro_year': 300,
    'pro_plus_month': 50,
    'pro_team_month': 0,
    'pro_team_year': 0,
    'smart_supplier_month': 0,  # grandfathered billing code only
    'lead_tokens_150': 0,       # grandfathered billing code only
}


def now():
    return int(time.time())


def source(value):
    return value if isinstance(value, str) and value in SOURCES else 'other'


def integer_env(key, default, minimum=0, maximum=100_000_000):
    try:
        value = int(os.getenv(key, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError(key)
        return value
    except ValueError:
        raise ValueError('Invalid revenue configuration: ' + key) from None


def configuration():
    """Return a stable catalogue version; live A/B price mutation is intentionally disabled."""
    return "subscription-catalog-v2", {"fixed": {"month": 49000, "year": 490000}}


def pricing(con, user):
    """Canonical four-tier catalogue; env overrides cannot silently change checkout prices."""
    plans = {
        code: {"amount_kopecks": item["amount_kopecks"], "duration_days": item["duration_days"]}
        for code, item in PUBLIC_PLANS.items()
    }
    catalog = []
    for code, item in PUBLIC_PLANS.items():
        catalog.append({
            "code": code,
            "title": item["title"],
            "period": item["period"],
            "tier": item["tier"],
            "amount_kopecks": item["amount_kopecks"],
            "duration_days": item["duration_days"],
            "features": list(item["features"]),
            "seat_limit": item.get("seat_limit"),
        })
    return {
        "experiment": "subscription-catalog-v2",
        "variant": "fixed",
        "plans": plans,
        "catalog": catalog,
        "annual_saving_kopecks": plans["pro_month"]["amount_kopecks"] * 12 - plans["pro_year"]["amount_kopecks"],
        "team_annual_saving_kopecks": plans["pro_team_month"]["amount_kopecks"] * 12 - plans["pro_team_year"]["amount_kopecks"],
        "purchase_bonus": {code: PURCHASE_BONUS_MESSAGES.get(code, 0) for code in PUBLIC_PLAN_CODES},
        "launch_offer": None,
        "limits": {"free_quotes": 10, "free_ai": 3, "pro_ai": 100, "pro_quotes": None},
    }

def record(con, uid, name, origin='', variant='', key=None):
    key = key or uuid.uuid4().hex
    return con.execute('INSERT INTO growth_events(id,user_id,name,source,variant,dedupe_key,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id',
                       (str(uuid.uuid4()), uid, name, source(origin) if origin else '', variant, key, now())).fetchone() is not None


def visit(con, user):
    record(con, user['id'], 'product_visit', key='visit:'+user['id']+':'+str(now()//86400))
    if user['entitlement_until'] and user['entitlement_until'] <= now():
        paid = con.execute("SELECT 1 FROM billing_intents b JOIN payments p ON p.id=b.payment_id WHERE b.user_id=? AND b.is_test=0 AND p.status='succeeded'",(user['id'],)).fetchone()
        if paid:
            record(con,user['id'],'subscription_expired',key='expired:'+user['id']+':'+str(user['entitlement_until']))


def activate(con, uid, name, quote_id):
    record(con, uid, name, key=name+':'+quote_id)
    if record(con, uid, 'activated', key='activation:'+uid):
        period = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')
        con.execute('UPDATE referral_rewards SET rewarded_at=?,period=? WHERE invitee_id=? AND rewarded_at IS NULL', (now(), period, uid))


def prepare_intent(
    con, user, key, plan, origin, is_test, expected_amount=None,
    workspace_id=None, auto_renew_requested=False, renewal_consent_version=None,
):
    previous = con.execute(
        'SELECT * FROM billing_intents WHERE user_id=? AND request_key=?',
        (user['id'], key),
    ).fetchone()
    if previous:
        if (
            previous['plan'] != plan
            or previous['is_test'] != int(is_test)
            or (expected_amount is not None and previous['amount_kopecks'] != expected_amount)
            or previous['workspace_id'] != workspace_id
            or bool(previous['auto_renew_requested']) != bool(auto_renew_requested)
            or previous['renewal_consent_version'] != (renewal_consent_version if auto_renew_requested else None)
        ):
            raise ValueError('Checkout key belongs to another plan, scope, or renewal choice')
        return previous
    offer = pricing(con, user)
    option = offer['plans'].get(plan)
    if not option:
        raise ValueError('Unknown pricing plan')
    if expected_amount is not None and expected_amount != option['amount_kopecks']:
        raise ValueError('Displayed price changed before checkout')
    if auto_renew_requested and (
        not isinstance(renewal_consent_version, str) or not renewal_consent_version.strip()
    ):
        raise ValueError('Renewal consent version is required')
    consent_at = now() if auto_renew_requested else None
    con.execute(
        'INSERT INTO billing_intents(id,user_id,request_key,plan,amount_kopecks,duration_days,variant,source,is_test,created_at,bonus_ai_messages,workspace_id,auto_renew_requested,renewal_consent_at,renewal_consent_version) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,request_key) DO NOTHING',
        (
            str(uuid.uuid4()), user['id'], key, plan, option['amount_kopecks'],
            option['duration_days'], offer['experiment']+':'+offer['variant'],
            source(origin), int(is_test), now(), offer['purchase_bonus'][plan],
            workspace_id, int(bool(auto_renew_requested)), consent_at,
            renewal_consent_version if auto_renew_requested else None,
        ),
    )
    return con.execute(
        'SELECT * FROM billing_intents WHERE user_id=? AND request_key=?',
        (user['id'], key),
    ).fetchone()


def payment_event(con, local, status, was_active=False):
    terms = con.execute('SELECT * FROM billing_intents WHERE payment_id=?', (local['id'],)).fetchone()
    # Mark the shop mode explicitly; legacy rows without verified mode remain unknown.
    if terms and not terms['is_test']:
        record(con, local['user_id'], {'succeeded':'payment_success','canceled':'checkout_cancelled'}[status], terms['source'], terms['variant'], 'payment:'+local['id']+':'+status)
        if status == 'succeeded':
            record(con, local['user_id'], 'subscription_renewed' if was_active else 'subscription_started', terms['source'], terms['variant'], 'subscription:'+local['id'])


def persist_checkout(con, user, key, plan, intent, remote):
    from backend.business import transaction
    with transaction(con):
        row = con.execute('SELECT * FROM payments WHERE user_id=? AND idempotency_key=?',(user['id'],key)).fetchone()
        if row:
            if row['plan']!=plan or row['provider_id']!=remote['id']:
                raise ValueError('Conflicting checkout')
            return row,False
        pid=str(uuid.uuid4())
        con.execute('INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,idempotency_key,confirmation_url,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (pid,user['id'],remote['id'],plan,intent['amount_kopecks'],'pending',key,remote['confirmation']['confirmation_url'],now()))
        con.execute('UPDATE billing_intents SET payment_id=? WHERE id=?',(pid,intent['id']))
        con.execute('INSERT INTO events(id,user_id,name,created_at) VALUES(?,?,?,?)',(str(uuid.uuid4()),user['id'],'checkout_started',now()))
        if not intent['is_test']:
            record(con,user['id'],'checkout_started',intent['source'],intent['variant'],'checkout:'+intent['id'])
        return con.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone(),True


def referral(con, user, code=None):
    own = con.execute('SELECT code FROM referral_links WHERE user_id=?', (user['id'],)).fetchone()
    if not own:
        con.execute('INSERT INTO referral_links(user_id,code,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO NOTHING', (user['id'], secrets.token_urlsafe(18), now()))
        own = con.execute('SELECT code FROM referral_links WHERE user_id=?', (user['id'],)).fetchone()
    if code:
        inviter = con.execute('SELECT r.user_id FROM referral_links r JOIN users u ON u.id=r.user_id WHERE r.code=? AND u.blocked=0 AND u.deleted_at IS NULL', (code,)).fetchone()
        active = con.execute("SELECT 1 FROM growth_events WHERE user_id=? AND name='activated'", (user['id'],)).fetchone()
        if inviter and inviter['user_id'] != user['id'] and not active and now()-user['created_at'] < 86400:
            con.execute('INSERT INTO referral_rewards(invitee_id,inviter_id,bonus,period) VALUES(?,?,3,?) ON CONFLICT(invitee_id) DO NOTHING', (user['id'], inviter['user_id'], dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')))
    rewards = con.execute('SELECT count(*) AS activated,coalesce(sum(bonus),0) AS bonus FROM referral_rewards WHERE inviter_id=? AND rewarded_at IS NOT NULL', (user['id'],)).fetchone()
    return {'code': own['code'], 'activated': rewards['activated'], 'bonus': rewards['bonus'], 'reward_ai': 3, 'monthly_bonus_cap': 30}


def referral_bonus(con, uid, period):
    row = con.execute('SELECT coalesce(sum(bonus),0) FROM referral_rewards WHERE inviter_id=? AND rewarded_at IS NOT NULL AND period=?', (uid, period)).fetchone()
    return min(30, row[0])


def pct(n, d):
    return round(n/d*100, 2) if d else None


def dashboard(con):
    t = now()
    start = t-30*86400
    # Only provider-verified LIVE payments, excluding full refunds, count as revenue.
    valid = "p.status='succeeded' AND b.is_test=0 AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')"
    totals = dict(con.execute(f'''SELECT coalesce(sum(p.amount_kopecks),0) AS revenue_all,
        coalesce(sum(CASE WHEN p.activated_at>=? THEN p.amount_kopecks ELSE 0 END),0) AS revenue_today,
        coalesce(sum(CASE WHEN p.activated_at>=? THEN p.amount_kopecks ELSE 0 END),0) AS revenue_7d,
        coalesce(sum(CASE WHEN p.activated_at>=? THEN p.amount_kopecks ELSE 0 END),0) AS revenue_30d,
        count(DISTINCT p.user_id) AS ever_paid FROM payments p JOIN billing_intents b ON b.payment_id=p.id WHERE {valid}''', ((t//86400)*86400,t-7*86400,start)).fetchone())
    population = dict(con.execute('SELECT count(*) AS users,sum(CASE WHEN entitlement_until>? AND blocked=0 THEN 1 ELSE 0 END) AS pro_access FROM users WHERE deleted_at IS NULL', (t,)).fetchone())
    paid = con.execute(f'''SELECT count(DISTINCT p.user_id) FROM payments p JOIN billing_intents b ON b.payment_id=p.id JOIN users u ON u.id=p.user_id WHERE {valid} AND u.entitlement_until>? AND u.deleted_at IS NULL AND u.blocked=0''', (t,)).fetchone()[0]
    mrr = con.execute(f'''SELECT coalesce(sum(CASE WHEN p.plan='pro_year' THEN p.amount_kopecks/12.0 ELSE p.amount_kopecks END),0) FROM payments p JOIN billing_intents b ON b.payment_id=p.id JOIN users u ON u.id=p.user_id WHERE {valid} AND u.entitlement_until>? AND u.deleted_at IS NULL AND u.blocked=0 AND p.id=(SELECT p2.id FROM payments p2 JOIN billing_intents b2 ON b2.payment_id=p2.id WHERE p2.user_id=p.user_id AND p2.status='succeeded' AND b2.is_test=0 AND NOT EXISTS(SELECT 1 FROM refunds r2 WHERE r2.payment_id=p2.id AND r2.status='succeeded') ORDER BY p2.activated_at DESC,p2.id DESC LIMIT 1)''', (t,)).fetchone()[0]
    funnel = {r['name']:r['users'] for r in con.execute('SELECT name,count(DISTINCT user_id) AS users FROM growth_events WHERE created_at>=? GROUP BY name', (start,))}
    intent_stats = dict(con.execute('''SELECT count(*) AS attempts,
        coalesce(sum(CASE WHEN p.status='succeeded' THEN 1 ELSE 0 END),0) AS succeeded,
        coalesce(sum(CASE WHEN p.status='canceled' THEN 1 ELSE 0 END),0) AS cancelled,
        coalesce(sum(CASE WHEN p.status='pending' THEN 1 ELSE 0 END),0) AS pending FROM billing_intents b LEFT JOIN payments p ON p.id=b.payment_id WHERE b.is_test=0 AND b.created_at>=?''', (start,)).fetchone())
    cohorts = []
    for day in (1,7,30):
        row = con.execute('''SELECT count(*) AS eligible,
            coalesce(sum(CASE WHEN EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='product_visit' AND e.created_at>=(u.created_at/86400)*86400+? AND e.created_at<(u.created_at/86400)*86400+?) THEN 1 ELSE 0 END),0) AS retained,
            coalesce(sum(CASE WHEN EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='payment_success' AND e.created_at>=u.created_at AND e.created_at<u.created_at+?) THEN 1 ELSE 0 END),0) AS paid
            FROM users u WHERE u.deleted_at IS NULL AND u.created_at>=? AND u.created_at/86400+?<?''', (day*86400,(day+1)*86400,day*86400,t-90*86400,day,t//86400)).fetchone()
        cohorts.append({'day':day, **dict(row), 'retention_pct':pct(row['retained'],row['eligible']), 'paid_pct':pct(row['paid'],row['eligible'])})
    # Daily signup cohorts use mature denominators; future days stay NULL, never fake zero.
    day_fields=[]
    for day in (1,7,30):
        mature=f'u.created_at/86400+{day}<{t//86400}'
        day_fields.extend((f'sum(CASE WHEN {mature} THEN 1 ELSE 0 END) AS eligible_d{day}',
            f"sum(CASE WHEN {mature} AND EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='product_visit' AND e.created_at/86400=u.created_at/86400+{day}) THEN 1 ELSE 0 END) AS retained_d{day}",
            f"sum(CASE WHEN {mature} AND EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='payment_success' AND e.created_at>=u.created_at AND e.created_at<u.created_at+{day*86400}) THEN 1 ELSE 0 END) AS paid_d{day}"))
    daily = [dict(r) for r in con.execute('''SELECT u.created_at/86400 AS signup_day,count(*) AS signups,
        sum(CASE WHEN EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='activated' AND e.created_at/86400=u.created_at/86400) THEN 1 ELSE 0 END) AS activation_d0
        ,'''+','.join(day_fields)+''' FROM users u WHERE u.deleted_at IS NULL AND u.created_at>=? GROUP BY u.created_at/86400 ORDER BY signup_day DESC''', (t-35*86400,))]
    for cohort in daily:
        for day in (1,7,30):
            cohort[f'retention_d{day}']=pct(cohort[f'retained_d{day}'],cohort[f'eligible_d{day}'])
            cohort[f'paid_pct_d{day}']=pct(cohort[f'paid_d{day}'],cohort[f'eligible_d{day}'])
    conversions = [dict(r) for r in con.execute('''SELECT b.source,b.variant,count(*) AS checkouts,
        sum(CASE WHEN p.status='succeeded' THEN 1 ELSE 0 END) AS paid,
        coalesce(sum(CASE WHEN p.status='succeeded' AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') THEN p.amount_kopecks ELSE 0 END),0) AS revenue_kopecks
        FROM billing_intents b LEFT JOIN payments p ON p.id=b.payment_id WHERE b.is_test=0 AND b.created_at>=? GROUP BY b.source,b.variant''', (start,))]
    by_source={(r['source'],r['variant']):r for r in conversions}
    for row in con.execute("SELECT source,variant,count(DISTINCT user_id) AS views FROM growth_events WHERE name='paywall_viewed' AND created_at>=? GROUP BY source,variant",(start,)):
        key=(row['source'],row['variant'])
        by_source.setdefault(key,{'source':key[0],'variant':key[1],'checkouts':0,'paid':0,'revenue_kopecks':0})['views']=row['views']
    conversions=list(by_source.values())
    estimates = con.execute("SELECT count(DISTINCT e.user_id) FROM events e JOIN users u ON u.id=e.user_id WHERE e.name='quote_created' AND u.deleted_at IS NULL").fetchone()[0]
    shares = con.execute('SELECT count(DISTINCT user_id) FROM quotes WHERE published_version>0').fetchone()[0]
    approvals = con.execute("SELECT count(DISTINCT user_id) FROM quotes WHERE approval_state='approved'").fetchone()[0]
    active = funnel.get('product_visit',0)
    activation_time=con.execute("SELECT count(*) AS activated,coalesce(sum(CASE WHEN e.first_at-u.created_at<180 THEN 1 ELSE 0 END),0) AS under_3m,avg(e.first_at-u.created_at) AS mean_seconds FROM users u JOIN (SELECT user_id,min(created_at) AS first_at FROM events WHERE name='quote_created' GROUP BY user_id) e ON e.user_id=u.id WHERE u.deleted_at IS NULL AND e.first_at>=u.created_at").fetchone()
    # Costs are estimates from explicit operator rates, never advertised as accounting data.
    fees = round(totals['revenue_30d']*integer_env('PAYMENT_FEE_BPS',0,0,10000)/10000)
    infrastructure = integer_env('INFRA_MONTHLY_KOPECKS',0)
    token_counts = con.execute('SELECT coalesce(sum(input_tokens),0) AS input,coalesce(sum(output_tokens),0) AS output FROM ai_usage WHERE created_at>=?', (start,)).fetchone()
    ai_cost = round((token_counts['input']*integer_env('AI_INPUT_KOPECKS_PER_MILLION',0)+token_counts['output']*integer_env('AI_OUTPUT_KOPECKS_PER_MILLION',0))/1_000_000)
    storage = integer_env('STORAGE_MONTHLY_KOPECKS',0)
    unknown_ai=con.execute("SELECT count(*) FROM ai_usage WHERE created_at>=? AND status='usage_unknown'",(start,)).fetchone()[0]
    unclassified = con.execute("SELECT count(*) FROM payments p LEFT JOIN billing_intents b ON b.payment_id=p.id WHERE p.status='succeeded' AND b.id IS NULL").fetchone()[0]
    # A conversion numerator must belong to its exposure cohort, not all payers.
    paywall_paid = con.execute("SELECT count(DISTINCT p.user_id) FROM payments p JOIN billing_intents b ON b.payment_id=p.id WHERE p.status='succeeded' AND b.is_test=0 AND b.created_at>=? AND EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=p.user_id AND e.name='paywall_viewed' AND e.created_at>=? AND e.created_at<=b.created_at)",(start,start)).fetchone()[0]
    expiry = con.execute(f'''SELECT count(DISTINCT u.id) AS baseline,coalesce(count(DISTINCT CASE WHEN u.entitlement_until<=? THEN u.id ELSE NULL END),0) AS expired FROM users u JOIN payments p ON p.user_id=u.id JOIN billing_intents b ON b.payment_id=p.id WHERE {valid} AND u.deleted_at IS NULL AND p.activated_at<? AND u.entitlement_until>=?''',(t,start,start)).fetchone()
    unit_users=[dict(r) for r in con.execute(f'''SELECT u.id,u.name,coalesce(r.revenue_kopecks,0) AS revenue_kopecks,coalesce(a.input_tokens,0) AS input_tokens,coalesce(a.output_tokens,0) AS output_tokens FROM users u LEFT JOIN (SELECT p.user_id,sum(p.amount_kopecks) AS revenue_kopecks FROM payments p JOIN billing_intents b ON b.payment_id=p.id WHERE {valid} AND p.activated_at>=? GROUP BY p.user_id) r ON r.user_id=u.id LEFT JOIN (SELECT user_id,sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens FROM ai_usage WHERE created_at>=? GROUP BY user_id) a ON a.user_id=u.id WHERE u.deleted_at IS NULL AND (r.user_id IS NOT NULL OR a.user_id IS NOT NULL) ORDER BY r.revenue_kopecks DESC,u.id LIMIT 50''',(start,start))]
    for person in unit_users:
        person['ai_cost_kopecks']=round((person.pop('input_tokens')*integer_env('AI_INPUT_KOPECKS_PER_MILLION',0)+person.pop('output_tokens')*integer_env('AI_OUTPUT_KOPECKS_PER_MILLION',0))/1_000_000)
        person['payment_fees_kopecks']=round(person['revenue_kopecks']*integer_env('PAYMENT_FEE_BPS',0,0,10000)/10000)
    return {'as_of':t, 'window_days':30, **totals, **population, 'paid_users':paid, 'free_users':population['users']-(population['pro_access'] or 0),
        'mrr_kopecks':round(mrr), 'arr_kopecks':round(mrr*12), 'recurring':False,
        'arpu_kopecks':round(totals['revenue_30d']/active) if active else None,
        'arppu_kopecks':round(totals['revenue_30d']/funnel['payment_success']) if funnel.get('payment_success') else None,
        'free_to_paid_pct':pct(totals['ever_paid'],population['users']), 'signup_to_estimate_pct':pct(estimates,population['users']),
        'estimate_to_share_pct':pct(shares,estimates), 'share_to_approval_pct':pct(approvals,shares),
        'activation_pct':pct(estimates,population['users']), 'paywall_conversion_pct':pct(paywall_paid,funnel.get('paywall_viewed',0)),
        'checkout_conversion_pct':pct(intent_stats['succeeded'],intent_stats['attempts']),
        'payment_success_pct':pct(intent_stats['succeeded'],intent_stats['succeeded']+intent_stats['cancelled']),
        'funnel':funnel, 'payments':intent_stats, 'cohorts':cohorts, 'signup_cohorts':daily, 'sources':conversions,'unit_users':unit_users,
        'first_estimate':{'mean_seconds':round(activation_time['mean_seconds']) if activation_time['mean_seconds'] is not None else None,'under_3m_pct':pct(activation_time['under_3m'],activation_time['activated'])},
        'trial_to_paid_pct':None, 'churn_pct':pct(expiry['expired'],expiry['baseline']), 'expired_subscriptions':expiry['expired'], 'ltv_kopecks':None,'unclassified_payments':unclassified,
        'economics':{'revenue_kopecks':totals['revenue_30d'],'ai_cost_kopecks':ai_cost,'payment_fees_kopecks':fees,'infrastructure_kopecks':infrastructure,
            'storage_kopecks':storage,'unknown_ai_requests':unknown_ai,'gross_margin_kopecks':totals['revenue_30d']-ai_cost-fees-infrastructure-storage,
            'costs_configured':all(os.getenv(key) is not None for key in ('PAYMENT_FEE_BPS','INFRA_MONTHLY_KOPECKS','STORAGE_MONTHLY_KOPECKS','AI_INPUT_KOPECKS_PER_MILLION','AI_OUTPUT_KOPECKS_PER_MILLION')) and (not unknown_ai or integer_env('AI_INPUT_KOPECKS_PER_MILLION',0)==integer_env('AI_OUTPUT_KOPECKS_PER_MILLION',0)==0)}}
