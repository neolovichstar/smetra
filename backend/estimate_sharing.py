"""Email-address-bound immutable estimate inbox and interactive decisions.

Published snapshots remain immutable. A changed set of optional rows requests
a new quote version, never mutates approved money without the contractor.
"""
import hashlib
import json
import re
import secrets
from backend.business import DomainError, calculate, identity, stamp, string
from backend.quote_integrity import verify_totals, InvalidSnapshot


def _email(value):
    if not isinstance(value,str) or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+",value.strip()) or len(value)>254:
        raise DomainError(400,"Укажите корректную почту клиента")
    return value.strip().lower()


def _load_snapshot(con,share):
    row=con.execute(
        "SELECT q.*,v.snapshot FROM quotes q JOIN quote_versions v "
        "ON v.quote_id=q.id AND v.version=? "
        "WHERE q.id=? AND q.workspace_id=?",
        (share["quote_version"],share["quote_id"],share["workspace_id"]),
    ).fetchone()
    if not row or row["published_version"]!=share["quote_version"]:
        raise DomainError(409,"Версия сметы изменилась. Запросите новую ссылку")
    snapshot=json.loads(row["snapshot"])
    try:
        verify_totals(snapshot,calculate)
    except (InvalidSnapshot,DomainError):
        raise DomainError(409,"Сохранённые расчёты сметы требуют проверки") from None
    return row,snapshot


def _public(snapshot):
    allowed=("title","client","description","terms","due_date","expires_at",
             "version","amount_kopecks","currency","itemized")
    output={key:snapshot[key] for key in allowed if key in snapshot}
    rows=[]
    for item in snapshot.get("items",[]):
        keys=("name","description","category","quantity","unit","unit_price",
              "optional","included","subtotal","tax","tax_amount","coefficient",
              "markup","discount")
        rows.append({key:item[key] for key in keys if key in item})
    output["items"]=rows
    return output


def _selection(snapshot,choice):
    items=snapshot.get("items",[])
    selectable={index for index,row in enumerate(items) if row.get("optional",False)}
    if not isinstance(choice,list) or len(choice)>len(selectable) or any(type(i) is not int for i in choice):
        raise DomainError(400,"Некорректный выбор строк")
    selected=set(choice)
    if len(selected)!=len(choice) or not selected<=selectable:
        raise DomainError(400,"Можно изменять только необязательные строки")
    # Normalize trusted publisher-owned line prices using the backend's money
    # engine, then sum only selected rows. No totals come from client or LLM.
    if not items:
        if choice:
            raise DomainError(400,"Эта смета не содержит дополнительных строк")
        return snapshot["amount_kopecks"], []
    normalized,_,_=calculate([{**row,"included":True} for row in items])
    return sum(row["subtotal"] for i,row in enumerate(normalized)
               if i not in selectable or i in selected), sorted(selected)


def _existing_selection(snapshot):
    return [i for i,row in enumerate(snapshot.get("items",[]))
            if row.get("optional") and row.get("included",True)]


def sender_route(service,method,parts,data):
    if method=="POST" and parts==[]:
        service.h.throttle("share-send:"+service.user["id"],5,3600)
        if service.role not in ("owner","admin","manager"):
            raise DomainError(403,"Недостаточно прав для отправки смет")
        if not service.user["email_verified_at"]:
            raise DomainError(403,"Подтвердите почту перед отправкой приглашений")
        quote_id=string(data.get("quote_id",""),"Смета",80,True)
        to=_email(data.get("email"))
        # One mailbox cannot be flooded by many free accounts.
        service.h.throttle("share-recipient:"+hashlib.sha256(to.encode()).hexdigest(),3,86400)
        row=service.get("quotes",quote_id)
        if not row["published_version"] or row["approval_state"] not in ("sent","viewed","changes_requested"):
            raise DomainError(409,"Сначала опубликуйте смету для согласования")
        if row["expires_at"] and row["expires_at"] <= stamp():
            raise DomainError(410,"Срок согласования истёк")
        owner, snapshot=_load_snapshot(service.con,dict(quote_id=row["id"],workspace_id=service.wid,quote_version=row["published_version"]))
        old=service.con.execute(
            "SELECT id FROM estimate_shares WHERE workspace_id=? AND quote_id=? "
            "AND quote_version=? AND recipient_email=? AND status='active'",
            (service.wid,row["id"],row["published_version"],to),
        ).fetchone()
        if old:
            return 200,{"id":old["id"],"status":"active","already_shared":True}
        share_id=identity()
        token=secrets.token_urlsafe(32)
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        expires=stamp()+14*86400
        recipient=service.con.execute(
            "SELECT id FROM users WHERE email=? AND deleted_at IS NULL AND blocked=0 "
            "AND email_verified_at IS NOT NULL",(to,),
        ).fetchone()
        if not recipient:
            # SMTP failures roll back share creation. This bounded synchronous
            # delivery is a transitional path; the next iteration moves email
            # to an outbox to avoid network calls while holding write locks.
            from backend.app import mail
            invite=service.origin+"/app?share="+share_id
            mail(to,"Вам отправлена смета в Сметре",invite+
                 "\n\nОткройте ссылку после регистрации с этим адресом. "
                 "Android: https://www.rustore.ru/catalog/app/ru.smetra.mobile")
        service.con.execute(
            "INSERT INTO estimate_shares "
            "(id,workspace_id,quote_id,quote_version,sender_user_id,recipient_email,"
            "token_hash,status,expires_at,created_at) "
            "VALUES(?,?,?,?,?,?,?,'active',?,?)",
            (share_id,service.wid,row["id"],row["published_version"],
             service.user["id"],to,token_hash,expires,stamp()),
        )
        if recipient:
            from backend.push import enqueue
            notification_id=identity()
            service.con.execute("INSERT INTO notifications VALUES(?,?,?,?,?)",
                (notification_id,service.wid,"Вам отправлена смета",row["id"],stamp()))
            enqueue(service.con,service.wid,notification_id,
                    "Сметра: новое предложение",
                    "Откройте приложение, чтобы посмотреть и согласовать смету.",
                    row["id"],recipient_user_id=recipient["id"])
        return 201,{"id":share_id,"status":"active",
                    "expires_at":expires}
    if method=="GET" and not parts:
        rows=service.con.execute(
            "SELECT s.id,s.quote_id,s.quote_version,s.recipient_email,s.status,"
            "s.expires_at,s.created_at FROM estimate_shares s "
            "WHERE s.workspace_id=? ORDER BY s.created_at DESC LIMIT 80",
            (service.wid,),
        ).fetchall()
        return 200,{"shares":[dict(row) for row in rows]}
    if method=="GET" and len(parts)==1:
        share=service.con.execute(
            "SELECT * FROM estimate_shares WHERE id=? AND workspace_id=?",
            (parts[0],service.wid)
        ).fetchone()
        if not share:
            raise DomainError(404,"Получатель не найден")
        response=service.con.execute(
            "SELECT selected_optional,total_kopecks,status,revision,updated_at "
            "FROM estimate_share_responses WHERE share_id=?",
            (share["id"],)
        ).fetchone()
        return 200,{"share":{
            key:share[key] for key in ("id","quote_id","quote_version","recipient_email",
                                      "status","created_at","expires_at")
        },"response":dict(response) if response else None}
    if method=="DELETE" and len(parts)==1:
        service.h.throttle("share-revoke:"+service.user["id"],30,3600)
        if service.role not in ("owner","admin","manager"):
            raise DomainError(403,"Недостаточно прав")
        updated=service.con.execute(
            "UPDATE estimate_shares SET status='revoked',revoked_at=? "
            "WHERE id=? AND workspace_id=? AND status='active'",
            (stamp(),parts[0],service.wid),
        )
        if updated.rowcount!=1:
            raise DomainError(404,"Активная ссылка не найдена")
        return 200,{"ok":True}
    raise DomainError(404,"Маршрут отправки не найден")


def _recipient_record(handler,con,user,share_id):
    if not re.fullmatch(r"[a-f0-9-]{36}",share_id):
        raise DomainError(404,"Сметра не найдена")
    if not user["email_verified_at"]:
        raise DomainError(403,"Сначала подтвердите почту")
    row=con.execute(
        "SELECT * FROM estimate_shares "
        "WHERE id=? AND recipient_email=? AND status='active' AND expires_at>?",
        (share_id,user["email"].lower(),stamp()),
    ).fetchone()
    if not row:
        raise DomainError(404,"Сметра не найдена")
    return row


def recipient_route(handler,con,method,path):
    user=handler.auth(con)
    if not user["email_verified_at"]:
        raise DomainError(403,"Сначала подтвердите почту")
    handler.throttle("shared-inbox:"+user["id"],60,60)
    parts=path.removeprefix("/api/shared-inbox").strip("/").split("/")
    if parts==[""] and method=="GET":
        rows=con.execute(
            "SELECT s.id,s.quote_id,s.quote_version,s.status,s.created_at,"
            "s.expires_at,q.title,q.currency FROM estimate_shares s "
            "JOIN quotes q ON q.id=s.quote_id WHERE s.recipient_email=? "
            "AND s.status='active' AND s.expires_at>? "
            "AND q.published_version=s.quote_version ORDER BY s.created_at DESC LIMIT 60",
            (user["email"].lower(),stamp()),
        ).fetchall()
        return 200,{"inbox":[dict(r) for r in rows]}
    if not parts or parts==[""]:
        raise DomainError(404,"Сметра не найдена")
    share=_recipient_record(handler,con,user,parts[0])
    quote,snapshot=_load_snapshot(con,share)
    saved=con.execute("SELECT * FROM estimate_share_responses WHERE share_id=?",
                      (share["id"],)).fetchone()
    selection=json.loads(saved["selected_optional"]) if saved else _existing_selection(snapshot)
    total,selection=_selection(snapshot,selection)
    if len(parts)==1 and method=="GET":
        return 200,{"share_id":share["id"],"quote":_public(snapshot),
                    "selected_optional":selection,"selected_total_kopecks":total,
                    "revision":saved["revision"] if saved else 0,
                    "status":saved["status"] if saved else "pending",
                    "requires_review":True}
    if len(parts)!=2 or parts[1] not in ("selection","approve") or method!="POST":
        raise DomainError(404,"Действие не найдено")
    data=handler.body()
    expected=data.get("revision")
    if type(expected) is not int or expected!=(saved["revision"] if saved else 0):
        raise DomainError(409,"Смета изменена в другом устройстве. Обновите страницу")
    if saved and saved["status"]!="draft":
        raise DomainError(409,"Ответ уже отправлен")
    if parts[1]=="selection":
        selected_total,selection=_selection(snapshot,data.get("included_optional"))
        status="draft"
    else:
        selected_total=total
        # Equal totals are not equal scopes: clients can swap identically
        # priced optional lines. Only the exact published set may be approved
        # without a new contractor-reviewed version.
        unchanged = selection == _existing_selection(snapshot)
        status="approved" if data.get("action")=="approve" and unchanged and total==snapshot["amount_kopecks"] else "changes_requested"
        if data.get("action") not in ("approve","request_changes"):
            raise DomainError(400,"Выберите действие по согласованию")
    now=stamp()
    from backend.business import transaction
    with transaction(con,lock_scopes=(f"workspace:{share['workspace_id']}",)):
        # Cross-instance optimistic revision guard on the recipient's only
        # writable response; PostgreSQL RLS remains enforced for runtime.
        if saved:
            change=con.execute(
                "UPDATE estimate_share_responses SET selected_optional=?,"
                "total_kopecks=?,status=?,revision=revision+1,updated_at=? "
                "WHERE share_id=? AND revision=? AND status='draft'",
                (json.dumps(selection),selected_total,status,now,share["id"],expected),
            )
            if change.rowcount!=1:
                raise DomainError(409,"Ответ уже изменился")
        else:
            con.execute(
                "INSERT INTO estimate_share_responses "
                "(share_id,recipient_user_id,selected_optional,total_kopecks,status,revision,updated_at) "
                "VALUES(?,?,?,?,?,1,?)",
                (share["id"],user["id"],json.dumps(selection),selected_total,status,now),
            )
        if parts[1]=="approve":
            if status=="approved":
                changed=con.execute(
                    "UPDATE quotes SET approval_state='approved',status='accepted',"
                    "approved_at=?,approved_by=?,updated_at=?,revision=revision+1 "
                    "WHERE id=? AND workspace_id=? AND published_version=? "
                    "AND approval_state IN ('sent','viewed','changes_requested')",
                    (now,user["name"],now,share["quote_id"],share["workspace_id"],share["quote_version"]),
                )
                if changed.rowcount!=1:
                    raise DomainError(409,"Сметра уже согласована или обновлена")
            from backend.push import enqueue
            nid=identity()
            label="Сметра согласована" if status=="approved" else "Клиент предложил изменения"
            con.execute("INSERT INTO notifications VALUES(?,?,?,?,?)",
                        (nid,share["workspace_id"],label,share["quote_id"],now))
            enqueue(con,share["workspace_id"],nid,label,
                    "Посмотрите ответ клиента в Сметре.",
                    share["quote_id"],recipient_user_id=share["sender_user_id"])
    return 200,{"status":status,"revision":expected+1,
                "selected_total_kopecks":selected_total,
                "quote_updated":status=="approved"}
