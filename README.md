# AI Web Platform

说出想法，生成网站，立即使用。

第一版跑通这条路径：注册、用一句话生成网站、预览、发布、分享，以及用部署 Agent 连上自己的服务器。AI 只产出经过校验的应用定义，运行时根据定义生成数据、接口和页面。

## 运行

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=".:../../packages/schema:../../packages/security" DATA_DIR="../../data" uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端：

```bash
cd apps/web
npm install
npm run dev
```

打开 http://127.0.0.1:5173

## 交给别人之前

不要把 `data/`、`services/api/.venv/`、`apps/web/node_modules/` 放进压缩包。本地账号、上传文件、签名私钥，以及这台电脑的路径都在这些目录里。源码本身不包含这些内容。

## 测试

```bash
cd services/api
PYTHONPATH=".:../../packages/schema:../../packages/security" .venv/bin/pytest
```
