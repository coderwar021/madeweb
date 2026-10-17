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
    if any(word in text for word in ("聊天", "聊天室", "群聊", "私信", "私聊", "即时通讯", "messenger", "chatroom", "チャット", "对话频道")):
        return "chat"
    if re.search(r"(?<![a-z])chat(?![a-z])", text):
        return "chat"
    if any(word in text for word in ("二手", "闲置", "市集", "买卖", "出售", "电商", "购物", "商店", "卖家", "marketplace", "classified", "中古", "フリマ", "マーケット")):
        return "marketplace"
    if any(word in text for word in ("商品",)) and any(word in text for word in ("交易", "卖", "买", "市场", "shop", "store")):
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
    if schema.get("template") == "chat":
        return "chat"
    return "app"


def plan_create(prompt: str) -> dict:
    kind = detect_template(prompt)
    if kind == "marketplace":
        return paint_schema(marketplace_schema(prompt))
    if kind == "chat":
        return paint_schema(chat_schema(prompt))
    if kind == "booking":
        return paint_schema(booking_schema(prompt))
    if kind == "blog":
        return paint_schema(blog_schema(prompt))
    return paint_schema(generic_schema(prompt))


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


def chat_schema(prompt: str) -> dict:
    topic = _topic(prompt)
    name = "夜聊"
    if topic and not topic.startswith("做") and "聊天" not in topic and "chat" not in topic.lower():
        name = topic
    tagline = "进房间说话，消息留在房间里。"
    return {
        "name": name[:40],
        "description": tagline,
        "template": "chat",
        "theme": _theme("#5b8def", "#0f1419", name[:24], tagline, "CNY"),
        "entities": [
            _entity(
                "Room",
                "房间",
                "public",
                "title",
                {
                    "title": _string("房间名", required=True, searchable=True),
                    "topic": _text("简介"),
                    "ownerId": _user("创建者"),
                },
            ),
            _entity(
                "Message",
                "消息",
                "public",
                "body",
                {
                    "body": _text("内容", required=True),
                    "authorId": _user("作者"),
                    "roomId": _relation("房间", "Room", required=True),
                },
            ),
        ],
        "pages": [
            _page(
                "Home",
                "/",
                [
                    {"type": "Hero", "title": name[:80], "subtitle": tagline},
                    {"type": "CardGrid", "source": "Room"},
                    {"type": "Form", "source": "Room", "mode": "create"},
                ],
            ),
            _page(
                "Room",
                "/rooms/:id",
                [
                    {"type": "Detail", "source": "Room"},
                    {"type": "Comment", "source": "Message"},
                    {"type": "Form", "source": "Message", "mode": "create"},
                ],
            ),
            _page("Login", "/login", [{"type": "AuthForm"}]),
        ],
        "nav": [{"label": "房间", "route": "/"}, {"label": "登录", "route": "/login"}],
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
    for name in ("Product", "Entry", "Post", "Service", "Room"):
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


def fits_intent(intent: str, schema: dict) -> bool:
    names = {item.get("name") for item in schema.get("entities") or [] if isinstance(item, dict)}
    template = schema.get("template")
    if intent == "chat":
        return bool(names & {"Room", "Message", "Chat"}) and "Product" not in names and template != "marketplace"
    if intent == "blog":
        return template != "marketplace" and "Product" not in names
    if intent == "booking":
        return template != "marketplace" and "Product" not in names
    if intent == "marketplace":
        return True
    return template != "marketplace"


def merge_identity(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    name = overlay.get("name")
    if isinstance(name, str) and name.strip() and name not in {"东京二手市集", "未命名网站"}:
        merged["name"] = name[:40]
        merged["theme"]["logo"] = name[:24]
    description = overlay.get("description")
    if isinstance(description, str) and description.strip() and "二手" not in description:
        merged["description"] = description[:200]
        merged["theme"]["tagline"] = description[:80]
    theme = overlay.get("theme") if isinstance(overlay.get("theme"), dict) else {}
    for key in ("primary", "background", "ink"):
        value = theme.get(key)
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            merged["theme"][key] = value
    return paint_schema(merged)


def paint_schema(schema: dict) -> dict:
    painted = copy.deepcopy(schema)
    theme = painted.get("theme") or {}
    name = painted.get("name") or "网站"
    tagline = theme.get("tagline") or painted.get("description") or ""
    primary = theme.get("primary") or "#1f4b99"
    background = theme.get("background") or "#f7f6f3"
    ink = theme.get("ink") or "#1c1917"
    template = painted.get("template") or "generic"
    entities = {item["name"]: item for item in painted.get("entities") or []}
    for page in painted.get("pages") or []:
        route = page.get("route")
        if template == "chat":
            page["ui"] = _ui_chat(name, tagline, primary, background, route)
        elif template == "marketplace":
            page["ui"] = _ui_market(name, tagline, primary, background, ink, route)
        elif template == "blog":
            source = "Post" if "Post" in entities else next(iter(entities), "Entry")
            page["ui"] = _ui_blog(name, tagline, primary, background, ink, route, source, _detail_route(painted, source))
        elif template == "booking":
            page["ui"] = _ui_booking(name, tagline, primary, background, ink, route)
        else:
            source = next((item for item in ("Entry", "Post", "Item") if item in entities), next(iter(entities), "Entry"))
            page["ui"] = _ui_generic(name, tagline, primary, background, ink, route, source, _detail_route(painted, source))
    return painted


def _node(tag: str, **kwargs) -> dict:
    node = {"tag": tag}
    node.update({key: value for key, value in kwargs.items() if value is not None})
    return node


def _ui_chat(name: str, tagline: str, primary: str, background: str, route: str) -> dict:
    shell = {"minHeight": "100vh", "background": background, "color": "#e8e6e3", "display": "flex", "flexDirection": "column"}
    if route == "/login":
        return _node("div", style=shell, children=[_ui_auth(primary)])
    if route == "/rooms/:id":
        return _node(
            "div",
            style={**shell, "height": "100vh"},
            children=[
                _node(
                    "header",
                    bind="detail",
                    entity="Room",
                    style={"padding": "16px 24px", "borderBottom": "1px solid rgba(255,255,255,0.08)", "display": "flex", "justifyContent": "space-between"},
                    children=[
                        _node("a", href="/", text="房间", style={"color": "#e8e6e3"}),
                        _node("h1", field="title", style={"fontSize": "20px"}),
                    ],
                ),
                _node(
                    "main",
                    bind="list",
                    entity="Message",
                    style={"flex": "1", "overflowY": "auto", "padding": "16px 24px", "display": "flex", "flexDirection": "column", "gap": "12px"},
                    children=[
                        _node(
                            "article",
                            style={"background": "#1a222c", "padding": "12px 16px", "borderRadius": "16px", "maxWidth": "640px"},
                            children=[
                                _node("span", field="authorId", style={"opacity": "0.6", "fontSize": "12px"}),
                                _node("p", field="body", style={"margin": "6px 0 0 0", "whiteSpace": "pre-wrap"}),
                            ],
                        )
                    ],
                ),
                _node(
                    "form",
                    bind="form",
                    entity="Message",
                    style={"display": "flex", "gap": "8px", "padding": "16px 24px", "borderTop": "1px solid rgba(255,255,255,0.08)"},
                    children=[
                        _node("textarea", field="body", placeholder="写一条消息", style={"flex": "1", "minHeight": "48px", "borderRadius": "12px", "padding": "12px", "border": "0"}),
                        _node("button", submit=True, text="发送", style={"background": primary, "color": "#fff", "border": "0", "borderRadius": "12px", "padding": "12px 18px"}),
                    ],
                ),
            ],
        )
    return _node(
        "div",
        style=shell,
        children=[
            _node(
                "header",
                style={"padding": "32px 24px 8px 24px"},
                children=[
                    _node("h1", text=name[:40], style={"fontSize": "36px"}),
                    _node("p", text=tagline[:80], style={"opacity": "0.7"}),
                    _node("nav", bind="nav", style={"display": "flex", "gap": "16px", "margin": "16px 0 0 0"}),
                ],
            ),
            _node(
                "main",
                style={"padding": "8px 24px 40px 24px", "maxWidth": "720px", "display": "flex", "flexDirection": "column", "gap": "16px"},
                children=[
                    _node(
                        "div",
                        bind="list",
                        entity="Room",
                        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
                        children=[
                            _node(
                                "a",
                                href="/rooms/:id",
                                style={"display": "block", "background": "#1a222c", "padding": "16px", "borderRadius": "16px", "color": "#e8e6e3"},
                                children=[
                                    _node("h2", field="title", style={"fontSize": "18px"}),
                                    _node("p", field="topic", style={"opacity": "0.65", "margin": "6px 0 0 0"}),
                                ],
                            )
                        ],
                    ),
                    _node(
                        "form",
                        bind="form",
                        entity="Room",
                        style={"display": "flex", "flexDirection": "column", "gap": "8px", "background": "#1a222c", "padding": "16px", "borderRadius": "16px"},
                        children=[
                            _node("input", field="title", placeholder="新房间名", style={"padding": "12px", "borderRadius": "12px", "border": "0"}),
                            _node("input", field="topic", placeholder="这间房聊什么", style={"padding": "12px", "borderRadius": "12px", "border": "0"}),
                            _node("button", submit=True, text="创建房间", style={"background": primary, "color": "#fff", "border": "0", "borderRadius": "12px", "padding": "12px"}),
                        ],
                    ),
                ],
            ),
        ],
    )


def _ui_market(name: str, tagline: str, primary: str, background: str, ink: str, route: str) -> dict:
    shell = {"minHeight": "100vh", "background": background, "color": ink}
    if route == "/login":
        return _node("div", style=shell, children=[_ui_auth(primary)])
    if route == "/sell":
        return _node("div", style={**shell, "padding": "32px"}, children=[_node("form", bind="form", entity="Product", children=_form_fields("上架商品", primary))])
    if route.startswith("/products/"):
        return _node("div", style={**shell, "padding": "32px"}, children=[_node("article", bind="detail", entity="Product", children=[_node("img", srcField="images"), _node("h1", field="title"), _node("p", field="price"), _node("p", field="description")])])
    bind = "Product"
    if route == "/favorites":
        bind = "Favorite"
    if route == "/messages":
        bind = "Message"
    if route == "/orders":
        bind = "Order"
    if route in {"/favorites", "/messages", "/orders"}:
        return _node("div", style={**shell, "padding": "32px"}, children=[_node("div", bind="list", entity=bind, children=[_node("p", field="title")])])
    return _node(
        "div",
        style=shell,
        children=[
            _node("header", style={"padding": "24px"}, children=[_node("h1", text=name[:40]), _node("p", text=tagline[:80]), _node("nav", bind="nav")]),
            _node("main", style={"padding": "0 24px 40px 24px"}, children=[_node("div", bind="search", entity="Product"), _node("div", bind="list", entity="Product", style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px"}, children=[_node("a", href="/products/:id", style={"background": "#fff", "borderRadius": "24px", "overflow": "hidden"}, children=[_node("img", srcField="images"), _node("h2", field="title"), _node("p", field="price")])])]),
        ],
    )


def _detail_route(schema: dict, source: str) -> str:
    for page in schema.get("pages") or []:
        if ":id" not in str(page.get("route") or ""):
            continue
        for component in page.get("components") or []:
            if component.get("type") == "Detail" and component.get("source") == source:
                return page["route"]
    return f"/{source.lower()}s/:id"


def _ui_blog(name: str, tagline: str, primary: str, background: str, ink: str, route: str, source: str, detail: str) -> dict:
    shell = {"minHeight": "100vh", "background": background, "color": ink, "maxWidth": "720px", "padding": "32px"}
    if route == "/login":
        return _node("div", style=shell, children=[_ui_auth(primary)])
    if route == "/new":
        return _node("div", style=shell, children=[_node("form", bind="form", entity=source, children=_form_fields("写下这篇", primary))])
    if ":id" in route:
        return _node("div", style=shell, children=[_node("article", bind="detail", entity=source, children=[_node("h1", field="title"), _node("p", field="body")])])
    return _node("div", style=shell, children=[_node("h1", text=name[:40]), _node("p", text=tagline[:80]), _node("nav", bind="nav"), _node("div", bind="list", entity=source, children=[_node("a", href=detail, children=[_node("h2", field="title"), _node("p", field="body")])])])


def _ui_booking(name: str, tagline: str, primary: str, background: str, ink: str, route: str) -> dict:
    shell = {"minHeight": "100vh", "background": background, "color": ink, "padding": "32px"}
    if route == "/login":
        return _node("div", style=shell, children=[_ui_auth(primary)])
    if route == "/book":
        return _node("div", style=shell, children=[_node("form", bind="form", entity="Appointment", children=_form_fields("预约", primary))])
    if ":id" in route:
        return _node("div", style=shell, children=[_node("article", bind="detail", entity="Service", children=[_node("h1", field="title"), _node("p", field="description")])])
    return _node("div", style=shell, children=[_node("h1", text=name[:40]), _node("p", text=tagline[:80]), _node("nav", bind="nav"), _node("div", bind="list", entity="Service", children=[_node("a", href="/services/:id", children=[_node("h2", field="title"), _node("p", field="price")])])])


def _ui_generic(name: str, tagline: str, primary: str, background: str, ink: str, route: str, source: str, detail: str) -> dict:
    shell = {"minHeight": "100vh", "background": background, "color": ink, "padding": "32px", "maxWidth": "800px"}
    if route == "/login":
        return _node("div", style=shell, children=[_ui_auth(primary)])
    if route == "/new":
        return _node("div", style=shell, children=[_node("form", bind="form", entity=source, children=_form_fields("提交", primary))])
    if ":id" in route:
        return _node("div", style=shell, children=[_node("article", bind="detail", entity=source, children=[_node("h1", field="title"), _node("p", field="summary"), _node("p", field="body")])])
    return _node("div", style=shell, children=[_node("h1", text=name[:40]), _node("p", text=tagline[:80]), _node("nav", bind="nav"), _node("div", bind="list", entity=source, children=[_node("a", href=detail, children=[_node("h2", field="title")])])])


def _ui_auth(primary: str) -> dict:
    return _node("div", bind="auth", style={"maxWidth": "400px", "padding": "48px 24px"}, children=[_node("h1", text="登录"), _node("p", text="用这个网站自己的账号。")])


def _form_fields(action: str, primary: str) -> list[dict]:
    return [
        _node("h1", text=action[:40]),
        _node("button", submit=True, text=action[:12], style={"background": primary, "color": "#fff", "border": "0", "borderRadius": "999px", "padding": "10px 20px"}),
    ]
