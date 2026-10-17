from __future__ import annotations

import copy
import re

from awp_security.prompt import clean_copy, sanitize_prompt

CITY_ALIASES = (
    ("东京", ("东京", "東京", "tokyo")),
    ("大阪", ("大阪", "osaka")),
    ("京都", ("京都", "kyoto")),
    ("北京", ("北京", "beijing")),
    ("上海", ("上海", "shanghai")),
    ("深圳", ("深圳", "shenzhen")),
    ("杭州", ("杭州", "hangzhou")),
)


def _city(prompt: str) -> str:
    text = prompt.lower()
    for name, aliases in CITY_ALIASES:
        if any(alias.lower() in text for alias in aliases):
            return name
    return "东京"


def detect_template(prompt: str) -> str:
    text = sanitize_prompt(prompt).lower()
    if any(word in text for word in ("二手", "闲置", "商品", "marketplace", "classified", "市集", "中古", "フリマ", "マーケット")):
        return "marketplace"
    if any(word in text for word in ("预约", "订位", "booking", "reservation", "挂号", "予約")):
        return "booking"
    if any(word in text for word in ("博客", "blog", "文章", "日记", "ブログ", "日記")):
        return "blog"
    return "generic"


def slug_base(schema: dict) -> str:
    if schema.get("template") == "marketplace":
        return "tokyo-market" if "东京" in schema.get("name", "") else "used-market"
    if schema.get("template") == "blog":
        return "field-notes"
    if schema.get("template") == "booking":
        return "booking"
    return "app"


def plan_create(prompt: str) -> dict:
    kind = detect_template(prompt)
    if kind == "marketplace":
        return marketplace_schema(prompt)
    if kind == "booking":
        return booking_schema(prompt)
    if kind == "blog":
        return blog_schema(prompt)
    return generic_schema(prompt)


def _mentions(text: str, word: str) -> bool:
    folded = word.lower()
    if re.search(r"[a-z]", folded):
        return re.search(rf"(?<![a-z]){re.escape(folded)}(?![a-z])", text) is not None
    return folded in text


def plan_edit(schema: dict, prompt: str) -> tuple[dict | None, str]:
    text = prompt.lower()
    updated = copy.deepcopy(schema)
    applied: list[str] = []
    skipped: list[str] = []
    catalog = (
        ("favorite", ("收藏", "favorite", "favorites", "wishlist", "お気に入り"), "收藏", _add_favorite),
        ("comment", ("评论", "comment", "comments", "留言", "コメント"), "评论", _add_comment),
        ("order", ("订单", "下单", "预订", "order", "orders", "注文"), "订单", _add_order),
        ("search", ("搜索", "search", "検索"), "搜索", _add_search),
    )
    matched = False
    for _key, words, label, apply in catalog:
        if not any(_mentions(text, word) for word in words):
            continue
        matched = True
        if apply(updated):
            applied.append(label)
        else:
            skipped.append(label)
    if not matched:
        return None, "我还不能安全地实现这个修改。可以试试：增加收藏、评论、订单或搜索。"
    if not applied:
        return None, "这个功能已经在当前版本里了。"
    return updated, "已添加" + "、".join(applied)


def marketplace_schema(prompt: str) -> dict:
    city = _city(prompt)
    name = f"{city}二手市集"
    tagline = "把还好用的东西，交给下一位邻居。"
    return {
        "name": name,
        "description": tagline,
        "template": "marketplace",
        "theme": _theme("#e23d28", "#f4f0e6", name, tagline, "JPY"),
        "entities": [
            _entity("Category", "分类", "public", "name", {"name": _string("名称", required=True, searchable=True)}),
            _entity(
                "Product",
                "商品",
                "public",
                "title",
                {
                    "title": _string("标题", required=True, searchable=True),
                    "description": _text("描述"),
                    "price": _decimal("价格", required=True),
                    "images": {"type": "file[]", "label": "图片"},
                    "categoryId": _relation("分类", "Category"),
                    "sellerId": _user("卖家"),
                    "status": _enum("状态", ["available", "reserved", "sold"], default="available"),
                    "location": _string("地点"),
                },
            ),
            _entity(
                "Favorite",
                "收藏",
                "private",
                "productId",
                {"userId": _user("用户"), "productId": _relation("商品", "Product", required=True)},
                unique=["userId", "productId"],
            ),
            _entity(
                "Message",
                "消息",
                "participant",
                "body",
                {
                    "body": _text("内容", required=True),
                    "senderId": _user("发送者"),
                    "recipientId": _user_ref("收件人", required=True, participant=True),
                    "productId": _relation("商品", "Product"),
                },
            ),
            _entity(
                "Order",
                "订单",
                "private",
                "status",
                {
                    "productId": _relation("商品", "Product", required=True),
                    "buyerId": _user("买家"),
                    "status": _enum("状态", ["pending", "confirmed", "cancelled"], default="pending"),
                },
            ),
        ],
        "pages": [
            _page(
                "Home",
                "/",
                [
                    {"type": "Hero", "title": name, "subtitle": tagline},
                    {"type": "Search", "entity": "Product", "placeholder": "搜索相机、书桌、自行车"},
                    {"type": "Filter", "entity": "Category", "field": "categoryId"},
                    {"type": "ProductGrid", "source": "Product"},
                ],
            ),
            _page("Sell", "/sell", [{"type": "Form", "source": "Product", "mode": "create"}]),
            _page("Favorites", "/favorites", [{"type": "ProductGrid", "source": "Favorite"}]),
            _page("Messages", "/messages", [{"type": "Table", "source": "Message"}]),
            _page("Orders", "/orders", [{"type": "Table", "source": "Order"}]),
            _page("Login", "/login", [{"type": "AuthForm"}]),
            _page("Product", "/products/:id", [{"type": "Detail", "source": "Product"}]),
        ],
        "nav": [
            {"label": "市集", "route": "/"},
            {"label": "发布", "route": "/sell"},
            {"label": "收藏", "route": "/favorites"},
            {"label": "消息", "route": "/messages"},
            {"label": "订单", "route": "/orders"},
        ],
    }


def blog_schema(prompt: str) -> dict:
    topic = _topic(prompt) or "野外笔记"
    tagline = "把想法写成可以阅读的页面。"
    return _content_site(
        name=topic,
        tagline=tagline,
        template="blog",
        primary="#2f5d50",
        entity=_entity(
            "Post",
            "文章",
            "public",
            "title",
            {
                "title": _string("标题", required=True, searchable=True),
                "body": _text("正文", required=True),
                "cover": {"type": "file", "label": "封面"},
                "authorId": _user("作者"),
            },
        ),
        source="Post",
        detail="/posts/:id",
    )


def booking_schema(prompt: str) -> dict:
    topic = _topic(prompt) or "预约本"
    tagline = "选一个时间，把事情约下来。"
    return {
        "name": topic,
        "description": tagline,
        "template": "booking",
        "theme": _theme("#8a4b2f", "#f7f3ee", topic, tagline, "CNY"),
        "entities": [
            _entity(
                "Service",
                "服务",
                "public",
                "title",
                {
                    "title": _string("名称", required=True, searchable=True),
                    "description": _text("介绍"),
                    "price": _decimal("价格"),
                    "duration": {"type": "integer", "label": "时长"},
                },
            ),
            _entity(
                "Appointment",
                "预约",
                "private",
                "guestName",
                {
                    "serviceId": _relation("服务", "Service", required=True),
                    "guestName": _string("姓名", required=True),
                    "slot": _string("时间", required=True),
                    "note": _text("备注"),
                    "bookedBy": _user("预约人"),
                },
            ),
        ],
        "pages": [
            _page(
                "Home",
                "/",
                [
                    {"type": "Hero", "title": topic, "subtitle": tagline},
                    {"type": "Search", "entity": "Service", "placeholder": "搜索服务"},
                    {"type": "CardGrid", "source": "Service"},
                ],
            ),
            _page("Book", "/book", [{"type": "Form", "source": "Appointment", "mode": "create"}]),
            _page("Login", "/login", [{"type": "AuthForm"}]),
            _page("Service", "/services/:id", [{"type": "Detail", "source": "Service"}]),
        ],
        "nav": [{"label": "服务", "route": "/"}, {"label": "预约", "route": "/book"}],
    }


def generic_schema(prompt: str) -> dict:
    topic = _topic(prompt) or "未命名网站"
    tagline = "由你的想法生成，数据、接口和权限已经准备好。"
    return _content_site(
        name=topic,
        tagline=tagline,
        template="generic",
        primary="#1f4b99",
        entity=_entity(
            "Entry",
            "内容",
            "public",
            "title",
            {
                "title": _string("标题", required=True, searchable=True),
                "summary": _text("摘要"),
                "cover": {"type": "file", "label": "图片"},
                "authorId": _user("作者"),
            },
        ),
        source="Entry",
        detail="/entries/:id",
    )


def _content_site(name: str, tagline: str, template: str, primary: str, entity: dict, source: str, detail: str) -> dict:
    return {
        "name": name[:40],
        "description": tagline,
        "template": template,
        "theme": _theme(primary, "#f7f6f3", name[:24], tagline, "CNY"),
        "entities": [entity],
        "pages": [
            _page(
                "Home",
                "/",
                [
                    {"type": "Hero", "title": name[:80], "subtitle": tagline},
                    {"type": "Search", "entity": source, "placeholder": "搜索"},
                    {"type": "CardGrid", "source": source},
                ],
            ),
            _page("Create", "/new", [{"type": "Form", "source": source, "mode": "create"}]),
            _page("Login", "/login", [{"type": "AuthForm"}]),
            _page("Detail", detail, [{"type": "Detail", "source": source}]),
        ],
        "nav": [{"label": "首页", "route": "/"}, {"label": "发布", "route": "/new"}],
    }


def _add_favorite(schema: dict) -> bool:
    if _has(schema, "Favorite"):
        return False
    target = _public_target(schema)
    if target is None:
        return False
    field_name = "productId" if target == "Product" else "targetId"
    schema["entities"].append(
        _entity(
            "Favorite",
            "收藏",
            "private",
            field_name,
            {"userId": _user("用户"), field_name: _relation("目标", target, required=True)},
            unique=["userId", field_name],
        )
    )
    _add_page(schema, "Favorites", "/favorites", [{"type": "ProductGrid", "source": "Favorite"}], "收藏")
    return True


def _add_comment(schema: dict) -> bool:
    if _has(schema, "Comment"):
        return False
    schema["entities"].append(
        _entity(
            "Comment",
            "评论",
            "public",
            "body",
            {
                "body": _text("评论", required=True),
                "authorId": _user("作者"),
                "targetId": _string("目标"),
            },
        )
    )
    _add_page(schema, "Comments", "/comments", [{"type": "Comment", "source": "Comment"}], "评论")
    return True


def _add_order(schema: dict) -> bool:
    if _has(schema, "Order"):
        return False
    target = _public_target(schema)
    if target is None:
        return False
    field_name = "productId" if target == "Product" else "targetId"
    schema["entities"].append(
        _entity(
            "Order",
            "订单",
            "private",
            "status",
            {
                field_name: _relation("目标", target, required=True),
                "buyerId": _user("买家"),
                "status": _enum("状态", ["pending", "confirmed", "cancelled"], default="pending"),
            },
        )
    )
    _add_page(schema, "Orders", "/orders", [{"type": "Table", "source": "Order"}], "订单")
    return True


def _add_search(schema: dict) -> bool:
    for page in schema.get("pages", []):
        if page.get("route") == "/" and any(item.get("type") == "Search" for item in page.get("components", [])):
            return False
    target = _public_target(schema) or schema["entities"][0]["name"]
    for page in schema.get("pages", []):
        if page.get("route") == "/":
            page["components"].insert(1, {"type": "Search", "entity": target, "placeholder": "搜索"})
            return True
    return False


def _public_target(schema: dict) -> str | None:
    for name in ("Product", "Entry", "Post", "Service"):
        for entity in schema.get("entities", []):
            if entity["name"] == name and entity.get("access") == "public":
                return name
    for entity in schema.get("entities", []):
        if entity.get("access") == "public":
            return entity["name"]
    return None


def _has(schema: dict, name: str) -> bool:
    return any(entity["name"] == name for entity in schema.get("entities", []))


def _add_page(schema: dict, title: str, route: str, components: list[dict], label: str) -> None:
    if any(page.get("route") == route for page in schema.get("pages", [])):
        return
    schema["pages"].append(_page(title, route, components))
    nav = schema.setdefault("nav", [])
    if len(nav) < 8 and all(item.get("route") != route for item in nav):
        nav.append({"label": label, "route": route})


def _topic(prompt: str) -> str:
    text = sanitize_prompt(prompt)
    text = text.split("，")[0]
    return clean_copy(text, 32)


def _theme(primary: str, background: str, logo: str, tagline: str, currency: str) -> dict:
    return {
        "primary": primary,
        "background": background,
        "ink": "#1c1917",
        "logo": clean_copy(logo, 24) or "网站",
        "tagline": clean_copy(tagline, 80),
        "currency": currency,
    }


def _entity(name: str, label: str, access: str, title_field: str, fields: dict, unique: list[str] | None = None) -> dict:
    entity = {"name": name, "label": label, "access": access, "titleField": title_field, "fields": fields}
    if unique:
        entity["unique"] = unique
    return entity


def _page(title: str, route: str, components: list[dict]) -> dict:
    return {"page": title, "route": route, "layout": "default", "components": components}


def _string(label: str, required: bool = False, searchable: bool = False) -> dict:
    spec = {"type": "string", "label": label}
    if required:
        spec["required"] = True
    if searchable:
        spec["searchable"] = True
    return spec


def _text(label: str, required: bool = False) -> dict:
    spec = {"type": "text", "label": label}
    if required:
        spec["required"] = True
    return spec


def _decimal(label: str, required: bool = False) -> dict:
    spec = {"type": "decimal", "label": label}
    if required:
        spec["required"] = True
    return spec


def _enum(label: str, values: list[str], default: str | None = None) -> dict:
    spec = {"type": "enum", "label": label, "values": values}
    if default:
        spec["default"] = default
    return spec


def _relation(label: str, target: str, required: bool = False) -> dict:
    spec = {"type": "relation", "label": label, "target": target}
    if required:
        spec["required"] = True
    return spec


def _user(label: str) -> dict:
    return {"type": "user", "label": label, "auto": "current"}


def _user_ref(label: str, required: bool = False, participant: bool = False) -> dict:
    spec = {"type": "user", "label": label}
    if required:
        spec["required"] = True
    if participant:
        spec["participant"] = True
    return spec
