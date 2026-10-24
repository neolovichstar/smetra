"""Standard headers for transactional mail sent through VK WorkSpace."""
from email.utils import formataddr, formatdate, make_msgid


def configure(message, sender):
    """Attach well-formed message metadata; do not forge DKIM or SPF headers.

    SPF and DKIM authentication must be configured at the authoritative DNS
    provider and signing mail server, not fabricated in the message body.
    """
    sender = sender.strip()
    # Keep envelope-from aligned with the authenticated mailbox.
    message["From"] = formataddr(("Сметра", sender))
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"
    return message
