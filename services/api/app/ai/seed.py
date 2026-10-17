from __future__ import annotations

import secrets

from app.auth import hash_password
from app.models import AppUser, Record
from app.settings import Settings
from app.util import dumps, new_id, utcnow

CATEGORIES = ("电子", "家具", "服饰", "书籍", "出行", "其他")
PRODUCTS = (
    ("奥林巴斯胶片相机", "26800", "电子", "涩谷", "快门声还在，附两卷过期胶卷。"),
    ("白橡木书桌", "12000", "家具", "中目黑", "桌面有使用痕迹，抽屉都还顺。"),
    ("旧西装外套", "9000", "服饰", "下北泽", "肩线还挺，适合秋天的单穿。"),
    ("岩波文库一箱", "4500", "书籍", "神保町", "二十四本，书页发黄，没有缺页。"),
    ("公路自行车", "32000", "出行", "世田谷", "刚换外胎，车架有一道浅划痕。"),
    ("随身听", "6800", "电子", "高圆寺", "能转，耳机孔有一点松。"),
)


def seed_marketplace(apps, settings: Settings, app_id: str) -> None:
    now = utcnow()
    seller = AppUser(
        id=new_id(),
        app_id=app_id,
        email=f"seller-{app_id[:8]}@users.invalid",
        name="佐藤美咲",
        password_hash=hash_password(secrets.token_urlsafe(24), settings.bcrypt_rounds),
        role="user",
        created_at=now,
    )
    apps.add(seller)
    categories: dict[str, str] = {}
    for name in CATEGORIES:
        record_id = new_id()
        categories[name] = record_id
        apps.add(
            Record(
                id=record_id,
                app_id=app_id,
                entity="Category",
                data=dumps({"name": name}),
                owner_id=seller.id,
                created_at=now,
                updated_at=now,
            )
        )
    for title, price, category, location, description in PRODUCTS:
        apps.add(
            Record(
                id=new_id(),
                app_id=app_id,
                entity="Product",
                data=dumps(
                    {
                        "title": title,
                        "description": description,
                        "price": price,
                        "images": [],
                        "categoryId": categories[category],
                        "sellerId": seller.id,
                        "status": "available",
                        "location": location,
                    }
                ),
                owner_id=seller.id,
                created_at=now,
                updated_at=now,
            )
        )
