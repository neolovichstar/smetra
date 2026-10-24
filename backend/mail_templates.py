"""Accessible, dark-neutral, multipart transactional email designs for Smetra."""
from html import escape


def action_html(title, url):
    # URL originates from the configured public origin + app-owned path,
    # never arbitrary user-provided HTML.
    safe_title = escape(title, quote=True)
    safe_url = escape(url, quote=True)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:34px 16px;background:#09090b;color:#f6f6f7;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;border-collapse:collapse">
<tr><td style="padding:12px 0 28px;font-size:25px;font-weight:800;letter-spacing:-1px;color:#fff">сметра<span style="color:#aaaab0">.</span></td></tr>
<tr><td style="border-top:1px solid #313136;padding:30px 0">
<p style="color:#a8a8b1;font-size:11px;letter-spacing:1.5px;margin:0 0 13px">ВАШ АККАУНТ</p>
<h1 style="font-size:28px;line-height:1.2;letter-spacing:-1px;margin:0 0 18px;color:#fff">{safe_title}</h1>
<p style="font-size:14px;line-height:1.7;color:#b9b9c0;margin:0 0 24px">Чтобы продолжить, откройте защищённую страницу Сметры.</p>
<a href="{safe_url}" style="display:inline-block;padding:15px 22px;background:#ececee;color:#080809;border-radius:9px;font-size:13px;font-weight:700;text-decoration:none">Продолжить в Сметре →</a>
<p style="font-size:11px;line-height:1.7;color:#888892;overflow-wrap:anywhere;margin:23px 0 0">Если кнопка не работает, скопируйте ссылку в браузер:<br>{safe_url}</p>
<p style="font-size:12px;line-height:1.7;color:#8f8f99;margin:22px 0 0">Если вы не запрашивали это письмо, просто проигнорируйте его.</p>
</td></tr>
<tr><td style="border-top:1px solid #313136;padding:22px 0;color:#9999a2;font-size:12px;line-height:1.6">Сметра · рабочее пространство<br>
<a href="mailto:support@smetra.online" style="color:#d8d8dc">support@smetra.online</a></td></tr>
</table></td></tr></table></body></html>"""
