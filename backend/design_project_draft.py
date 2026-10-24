"""Opt-in PDF design-project preview, explicitly not an approved estimate."""
from backend.business import DomainError
from backend import ai


def draft(service, data):
    file=data.get("file")
    if not isinstance(file,dict) or file.get("mime")!="application/pdf":
        raise DomainError(400,"Выберите PDF дизайн-проекта")
    service.h.throttle("design-pdf:"+service.user["id"],3,300)
    annotation=data.get("instructions","")
    if not isinstance(annotation,str) or len(annotation)>1500:
        raise DomainError(400,"Слишком длинное описание проекта")
    task=(
        "Предварительный разбор дизайн-проекта. Извлеки только явно "
        "присутствующие ведомости отделки, экспликации, материалы и объёмы. "
        "Не подменяй измерения догадками. Неизвестные единицы и цены "
        "требуют ручной проверки. Ничего не публикуй.\n"+annotation
    )
    status,result=ai.draft(service,{"file":file,"text":task})
    return status,{**result,"source":"design_pdf","requires_review":True,
                   "published":False}
