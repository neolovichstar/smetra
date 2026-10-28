"""Isolated local-only accounts for the browser profile regression flow."""

import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    from scripts.fixture_network import restrict_to_loopback
    restrict_to_loopback()
    if (
        os.getenv("DATABASE_URL")
        or os.getenv("RUNTIME_DATABASE_URL")
        or os.getenv("VERCEL")
    ):
        raise RuntimeError("Browser fixture requires an isolated local database")
    os.environ["ALLOW_UNVERIFIED_SIGNUP"] = "1"
    from tests.test_public_profiles import PublicProfilesTests

    PublicProfilesTests.setUpClass()
    PublicProfilesTests.mod.ORIGIN = PublicProfilesTests.base
    PublicProfilesTests.mod.BROWSER_ORIGINS = frozenset((PublicProfilesTests.base,))
    import backend.community as community

    community.ORIGIN = PublicProfilesTests.base
    fixture = PublicProfilesTests()
    fixture.setUp()
    owner, oid = fixture.person("browser-owner")
    recipient, rid = fixture.person("browser-client")
    with fixture.mod.db() as con:
        con.execute("UPDATE users SET name='Константин Муравьёв' WHERE id=?", (oid,))
        con.execute("UPDATE users SET name='Анна Иванова' WHERE id=?", (rid,))
    profiles = []
    for token, name, handle, headline, city, bio in [
        (
            owner,
            "Константин Муравьёв",
            "konstantin_build",
            "Ремонт и отделка квартир",
            "Москва",
            "От замера до готового ремонта. Помогу рассчитать работы, подобрать материалы и согласовать понятную смету.\nРаботаю с частными заказчиками и командами.",
        ),
        (
            recipient,
            "Анна Иванова",
            "anna_design",
            "Дизайн интерьеров",
            "Казань",
            "Создаю уютные пространства. Открыта к сотрудничеству с мастерами и строительными командами.",
        ),
    ]:
        profiles.append(
            fixture.public(
                token,
                display_name=name,
                handle=handle,
                headline=headline,
                city=city,
                bio=bio,
            )
        )
    quote = fixture.publish(
        owner, fixture.quote(owner, title="Отделка квартиры · 64 м²")
    )
    fixture.quote(owner, title="Неопубликованный черновик")
    wid = fixture.call("/workspace", token=owner)[1]["workspace"]["id"]
    with fixture.mod.db() as con:
        con.execute(
            "UPDATE workspaces SET plan='team_month',subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?",
            (fixture.mod.now() + 86400, wid),
        )
    data = {
        "base": fixture.base,
        "owner": {"token": owner, "id": oid},
        "recipient": {"token": recipient, "id": rid},
        "profiles": profiles,
        "quote": quote,
        "workspace": wid,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    Path(
        os.getenv("SMETRA_PROFILE_FIXTURE", str(ROOT / "data/profile-fixture.json"))
    ).write_text(json.dumps(data))
    from PIL import Image, ImageDraw

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    image = Image.new("RGB", (800, 600), "#273c37")
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 0, 700, 620), fill="#c8d6c7")
    draw.polygon([(200, 600), (400, 210), (650, 600)], fill="#4a7163")
    image.save(data_dir / "profile-avatar.png")
    print("PROFILE_FIXTURE_READY", flush=True)
    signal.pause()


if __name__ == "__main__":
    main()
