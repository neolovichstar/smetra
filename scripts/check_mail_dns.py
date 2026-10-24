import json
import sys
import urllib.parse
import urllib.request

DOMAIN = "smetra.online"
RESOLVERS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")


def query(resolver, name, kind):
    url = resolver + "?" + urllib.parse.urlencode({"name": name, "type": kind})
    request = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    return [entry["data"].strip(chr(34)) for entry in data.get("Answer", ())
            if entry.get("type") == (16 if kind == "TXT" else 15)]


def check(resolver):
    txt = query(resolver, DOMAIN, "TXT")
    spf = [value for value in txt if value.lower().startswith("v=spf1 ")]
    mx = query(resolver, DOMAIN, "MX")
    dkim = query(resolver, "mailru._domainkey." + DOMAIN, "TXT")
    dmarc = query(resolver, "_dmarc." + DOMAIN, "TXT")
    return {
        "MX": any("emx.mail.ru" in value.lower() for value in mx),
        "SPF": len(spf) == 1 and "_spf.mail.ru" in spf[0],
        "DKIM": any(value.lower().startswith("v=dkim1") for value in dkim),
        "DMARC": any(value.lower().startswith("v=dmarc1") for value in dmarc),
    }


if __name__ == "__main__":
    passed = True
    for resolver in RESOLVERS:
        try:
            result = check(resolver)
            print(resolver, result)
            passed = all(result.values()) and passed
        except Exception as exc:
            print(resolver, "error:", type(exc).__name__)
            passed = False
    print("DNS OK; inspect real email headers for SPF/DKIM/DMARC pass"
          if passed else "DNS incomplete: fix Cloudflare records")
    sys.exit(0 if passed else 1)
