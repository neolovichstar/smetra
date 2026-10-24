# Доставляемость писем Сметры через VK WorkSpace

DNS-аудит 24.10.2026: smetra.online обслуживается DNS Cloudflare.
Два публичных резолвера (Cloudflare и Google) не находят MX, SPF, DKIM и DMARC.
Есть только TXT верификации mailru-domain: UQnzfKGMGVOWLYk5 — её сохранять.

## Записи для Cloudflare → DNS → Records

Тип | Имя | Значение | Приоритет | TTL
--- | --- | --- | --- | ---
MX | @ | emx.mail.ru | 10 | Auto
TXT | @ | v=spf1 redirect=_spf.mail.ru | — | Auto
TXT | mailru._domainkey | индивидуальное значение DKIM из VK WorkSpace → Состояние сервера | — | Auto
TXT | _dmarc | v=DMARC1; p=none; adkim=r; aspf=r; pct=100 | — | Auto

DKIM индивидуален для домена. Не вставлять чужой ключ или пример.
SPF-запись должна быть только одна: при появлении других легальных сервисов объединить её.
Сначала политика DMARC p=none, потом после проверки alignment переходить к quarantine/reject.
Не удалять другие A/AAAA/CNAME и TXT сайта. MX и TXT не проксируются через Cloudflare.

## Приёмка

1. Добавить записи DNS Cloudflare.
2. Проверить состояние MX/SPF/DKIM в панели администратора VK WorkSpace.
3. Выполнить python3 scripts/check_mail_dns.py.
4. Отправить код с сайта на почту в Gmail и Mail.ru.
5. В исходном письме проверить Authentication-Results: SPF=pass, DKIM=pass, DMARC=pass;
   домен аутентификации должен совпадать или быть выровнен со smetra.online.
6. Проверить папку Входящие и наблюдать жалобы и репутацию. Даже корректные DNS не гарантируют Inbox.

Источники:
https://www.workspacevk.com/blog/kak-sozdat-korporativnuyu-pochtu-mail-ru/
https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/
https://help.mail.ru/developers/notes/authentication/

Технические заголовки Date и Message-ID добавлены в Python для новых писем, вместе с
именем отправителя Сметра, multipart HTML/plain, Reply-To support@smetra.online.
Эти улучшения не заменяют настройку DNS.
