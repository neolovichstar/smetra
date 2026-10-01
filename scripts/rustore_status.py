"""Read RuStore release status without storing the API private key."""

import argparse
import base64
import datetime as dt
import getpass
import json
import urllib.error
import urllib.request


API = "https://public-api.rustore.ru"


def request(path, *, payload=None, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Public-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        API + path,
        None if payload is None else json.dumps(payload).encode(),
        headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                "RuStore HTTP 403: проверьте разрешённые методы и приложения ключа; "
                "API публикации требует хотя бы одну активную версию"
            ) from None
        raise RuntimeError(f"RuStore HTTP {error.code}") from None
    if result.get("code") != "OK":
        raise RuntimeError(f"RuStore API: {result.get('message') or 'request failed'}")
    return result.get("body") or {}


def authenticate(key_id, encoded_key):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = serialization.load_der_private_key(
        base64.b64decode(encoded_key.strip(), validate=True), password=None
    )
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    signature = private_key.sign(
        (key_id + timestamp).encode(), padding.PKCS1v15(), hashes.SHA512()
    )
    body = request("/public/auth/", payload={
        "keyId": key_id,
        "timestamp": timestamp,
        "signature": base64.b64encode(signature).decode(),
    })
    return body["jwe"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key_id")
    parser.add_argument("--package", default="ru.smetra.mobile")
    args = parser.parse_args()
    private_key = getpass.getpass("RuStore private key: ")
    token = authenticate(args.key_id, private_key)
    private_key = None
    apps = request("/public/v1/application", token=token).get("content", [])
    selected = next((item for item in apps if item.get("packageName") == args.package), None)
    if selected is None:
        print("Package is not accessible to this API key")
        return 2
    print(json.dumps({key: selected.get(key) for key in (
        "packageName", "appStatus", "versionName", "versionCode", "deviceType"
    )}, ensure_ascii=False))
    versions = request(
        f"/public/v1/application/{args.package}/version?page=0&size=20", token=token
    ).get("content", [])
    for version in versions:
        print(json.dumps({key: version.get(key) for key in (
            "versionId", "versionName", "versionCode", "versionStatus", "testingType"
        )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
