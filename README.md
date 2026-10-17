# AI Web Platform

说出想法，生成网站，立即使用。

Say it. Build it. Share it.  
話して、つくって、すぐ使う。

用一句话描述想要的网站。平台生成一个可以注册、登录、发布内容、上传图片、搜索和分享的网站。界面提供中文、日文和英文。

## 使用路径

1. 注册平台账号。
2. 输入一句话，查看生成过程。
3. 在预览里使用这个网站。
4. 保存版本，然后发布。
5. 分享公开地址，或在此基础上继续修改。

发布时可以选择放在平台上，或装到自己的服务器。自己的服务器通过向外连接的部署代理接收任务。平台不会登录那台机器。

示例：

> 做一个东京二手交易网站，用户可以发布商品、上传图片、搜索、收藏和联系卖家。

生成结果先写成经过校验的应用定义。运行时根据这个定义提供数据、接口和页面。用 AI 修改时，可以加入收藏、评论、订单和搜索。

## 环境

- Python 3.13
- Node.js 22
- npm

## 本地运行

安装并启动接口：

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=".:../../packages/schema:../../packages/security" DATA_DIR="../../data" uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端，启动页面：

```bash
cd apps/web
npm install
npm run dev
```

打开 http://127.0.0.1:5173 。页面会把 `/api` 转发到 http://127.0.0.1:8000 。

## 部署

把本仓库连接到 Railway 后直接部署。Railpack 会安装后端依赖、构建页面，并用同一个地址提供网站和接口。不需要填写启动命令，也不需要再开第二个服务。

## 根管理员

环境变量里只有邮箱，没有超级管理员账号名，也没有密码。

1. 在部署平台设置 `ADMIN_EMAILS`，例如 `admin@example.com`。多个邮箱用英文逗号分隔。
2. 打开网站，走普通注册。
3. 邮箱填写上面那一个，密码在注册页自己设置。

用这个邮箱注册出来的账号就是根管理员，可以管理用户和审核网站。密码只存在这个账号里，改环境变量不会改掉已经设置的密码。

## 生成网站

不设置 `AI_API_KEY` 时，平台用本地模板生成网站：二手市集、预约、博客，或通用站点。页面上的生成过程不是外部模型在思考。

要让模型真正参与生成，在部署平台加上这些变量：

| 变量 | 作用 |
| --- | --- |
| `AI_API_KEY` | 模型接口密钥。不设置时只用本地模板。 |
| `AI_BASE_URL` | OpenAI 兼容地址，默认 `https://api.openai.com/v1`。 |
| `AI_MODEL` | 模型名，默认 `gpt-4o-mini`。 |

密钥只留在环境变量里，不会写进生成结果、日志或 Git。模型返回的内容会先经过校验；过不了就退回本地模板。

## 下架和删除

网站主人可以在「我的网站」、预览页和发布页下架或删除。

- 下架：从探索页拿下来，公开地址别人再也打不开。草稿还在，可以继续改，再发布。
- 删除：网站从你的列表里消失，公开地址关闭。数据会再留 `RETENTION_DAYS` 天后清掉。

审核员看到举报后，也可以把网站下架。

可选环境变量：

| 变量 | 作用 |
| --- | --- |
| `ADMIN_EMAILS` | 根管理员邮箱，逗号分隔。只用来识别谁是根管理员，不包含密码。 |
| `AI_API_KEY` | 可选。填了才会调用模型生成网站。 |
| `AI_BASE_URL` | 可选。模型接口地址。 |
| `AI_MODEL` | 可选。模型名。 |
| `DATA_DIR` | 数据库、上传文件和签名密钥的目录。默认是仓库下的 `data/`。 |
| `DATABASE_URL` | 平台库连接串。不设置时使用 `DATA_DIR` 里的 SQLite。 |
| `APPS_DATABASE_URL` | 生成网站的数据库连接串。不设置时使用另一份 SQLite。 |
| `PUBLIC_API_BASE` | 对外公布的接口地址，供部署代理解析。Railway 上会使用 `RAILWAY_PUBLIC_DOMAIN`。 |
| `COOKIE_SECURE` | 设为 `1` 时，登录 Cookie 只在 HTTPS 下发送。公开地址是 `https://` 时会自动打开。 |
| `CORS_ORIGINS` | 允许携带 Cookie 的页面来源，逗号分隔。 |
| `BCRYPT_ROUNDS` | 密码哈希轮数，默认 `12`。 |
| `RETENTION_DAYS` | 软删除数据的保留天数，默认 `30`。 |

## 目录

```text
apps/web                 平台页面和生成网站的运行界面
services/api             平台接口
packages/schema          应用定义的校验
packages/security        签名、日志脱敏、地址检查和图片检查
agent/deployment-agent   安装在自己服务器上的部署代理
```

平台账号和每个生成网站里的用户是分开的。平台数据与网站数据也分开放。

## 自己的服务器

在发布页面选择自己的服务器后，页面会给出安装命令。代理登记到平台后，只执行这些动作：

`DEPLOY`、`START`、`STOP`、`RESTART`、`ROLLBACK`、`STATUS`、`LOGS`

本地直接运行时代理不会启动容器。

## 测试

```bash
cd services/api
PYTHONPATH=".:../../packages/schema:../../packages/security" .venv/bin/pytest
```

## 安全

边界和实现说明写在 [SECURITY.md](SECURITY.md)。生成过程把用户输入当作数据。密钥不会进入提示词、生成结果、日志或 Git。日志里的敏感内容会显示为 `[REDACTED]`。

以下内容留在本机，不进入仓库：

- `data/`：数据库、上传文件、签名私钥
- `services/api/.venv/`
- `apps/web/node_modules/`
- `.env`
