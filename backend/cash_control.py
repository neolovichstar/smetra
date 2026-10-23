"""Cash warnings use posted money, not quote revenue or invented balances."""
from backend.business import identity, stamp


def update_project_risk(service, project_id):
    from backend.entitlements import workspace_feature_access
    if not workspace_feature_access(service.con, service.wid, "finance", stamp())["allowed"]:
        return None
    project = service.get("projects", project_id)
    paid = service.con.execute(
        "SELECT coalesce(sum(amount_kopecks),0) FROM project_payments WHERE project_id=? AND workspace_id=?",
        (project_id, service.wid)).fetchone()[0]
    spent = service.con.execute(
        "SELECT coalesce(sum(amount_kopecks),0) FROM expenses WHERE project_id=? AND workspace_id=?",
        (project_id, service.wid)).fetchone()[0]
    deficit = max(0, spent - paid)
    previous = service.con.execute("SELECT * FROM project_cash_risks WHERE project_id=? AND workspace_id=?",
                                   (project_id, service.wid)).fetchone()
    prior_deficit = previous["deficit_kopecks"] if previous else 0
    if previous:
        service.con.execute(
            "UPDATE project_cash_risks SET deficit_kopecks=?,active=?,revision=revision+1,updated_at=? WHERE id=?",
            (deficit, int(deficit > 0), stamp(), previous["id"]))
    else:
        service.insert("project_cash_risks", dict(id=identity(), workspace_id=service.wid,
                       project_id=project_id, deficit_kopecks=deficit, active=int(deficit > 0),
                       updated_at=stamp()))
    # An increase or a new episode warrants a warning. Replayed writes never reach here.
    if deficit > prior_deficit:
        owner = service.con.execute("SELECT owner_id FROM workspaces WHERE id=?", (service.wid,)).fetchone()[0]
        nid = identity()
        service.con.execute("INSERT INTO notifications(id,workspace_id,message,entity_id,created_at) VALUES(?,?,?,?,?)",
                            (nid, service.wid, "Риск кассового разрыва по заказу", project_id, stamp()))
        from backend.push import enqueue
        enqueue(service.con, service.wid, nid, "Проверьте финансы объекта",
                "Есть риск превышения доступных средств. Подробности в Сметре.", project_id,
                recipient_user_id=owner)
    return {"project_id": project["id"], "currency": project["currency"],
            "received_kopecks": paid, "spent_kopecks": spent, "deficit_kopecks": deficit}
