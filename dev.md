一、《AI Web Platform》开发技术设计文档
1. 产品定义

暂定名称：

AI Web Platform

核心 Slogan：

Say it. Build it. Share it.

中文：

说出想法，生成网站，立即使用。

产品不是传统 AI Coding Agent。

用户不需要：

写代码
配数据库
写 API
配服务器
配权限
配部署
配域名

用户只需要：

告诉 AI 想做什么。

平台负责生成一个真正可以运行的 Web App。

2. 核心产品模型

整个系统由四层组成：

┌────────────────────────────────────┐
│             AI Builder             │
│                                    │
│ Prompt → Plan → Schema → UI/API   │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│          Application Runtime       │
│                                    │
│ Auth / DB / API / Storage /       │
│ Permission / Workflow / Plugin    │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│          Deployment Engine         │
│                                    │
│ Cloud / User Server / Docker       │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│          Published Website         │
│                                    │
│ xxx.platform.com / Custom Domain  │
└────────────────────────────────────┘
3. 三种用户模式
模式 A：平台托管

用户：

创建网站

平台自动：

生成
↓
构建
↓
部署
↓
分配域名

最终：

https://abc.platform.com
模式 B：自定义服务器

用户输入：

Server IP
SSH Port
Username
SSH Key

平台建立：

Platform
   ↓
Secure Deployment Agent
   ↓
User Server

最终网站运行在：

用户自己的服务器
模式 C：完全自托管

后期提供：

curl ... | sh

用户安装：

AI Web Runtime

然后：

在自己的服务器上运行整个系统。

这个模式以后可以成为企业版核心能力。

4. 网站模型

平台不应该把网站直接定义成：

一堆源码。

而是：

Application Definition

例如：

{
  "name": "Tokyo Used Market",
  "version": "1.0.0",
  "pages": [],
  "entities": [],
  "actions": [],
  "permissions": [],
  "workflows": [],
  "theme": {}
}
5. Entity 模型

例如用户说：

做一个二手交易网站。

AI 创建：

User
Product
Category
Favorite
Message
Order

每个 Entity：

{
  "name": "Product",
  "fields": {
    "title": "string",
    "description": "text",
    "price": "decimal",
    "images": "file[]",
    "sellerId": "user",
    "status": "enum"
  }
}

Runtime 根据 Schema 自动生成：

数据库表
API
CRUD
权限
前端表单
6. 页面模型
{
  "page": "Home",
  "route": "/",
  "layout": "default",
  "components": [
    {
      "type": "Hero"
    },
    {
      "type": "ProductGrid",
      "source": "Product"
    }
  ]
}
7. UI 组件系统

平台维护自己的组件库。

例如：

Layout
Navbar
Sidebar
Hero
Card
Table
Form
Modal
Drawer
Tabs
Upload
Search
Filter
Chart
Map
Chat
Comment
Pagination

AI 不允许随意生成 UI 基础组件。

而是：

选择 + 配置组件。

这样可以保证：

UI 稳定
性能稳定
安全
视觉统一
AI 修改不会把整个项目搞坏
8. AI Architecture

核心 Pipeline：

User Prompt
     ↓
Intent Parser
     ↓
Requirement Planner
     ↓
App Schema Generator
     ↓
Schema Validator
     ↓
UI Planner
     ↓
Backend Planner
     ↓
Permission Planner
     ↓
Build
     ↓
Test
     ↓
Deploy
9. AI 不直接拥有生产权限

这是架构原则。

错误方式：

LLM
 ↓
SSH
 ↓
服务器

绝对不要这么做。

正确：

LLM
 ↓
Structured Plan
 ↓
Validator
 ↓
Build System
 ↓
Deployment System
 ↓
Deployment Agent
 ↓
Server

AI 永远不能直接：

ssh root
rm -rf
docker exec
10. AI 修改网站

用户：

“增加一个收藏功能。”

AI 不重新生成整个项目。

生成：

{
  "operation": "ADD_FEATURE",
  "entity": "Favorite",
  "relations": [...],
  "pages": [...],
  "permissions": [...]
}

然后：

Schema Diff
↓
Validation
↓
Migration
↓
Build
↓
Test
↓
Deploy
11. Version System

每次 AI 修改都产生版本：

v1
v2
v3
v4

用户可以：

Restore v2

同时支持：

Remix

用户 A：

My Website
v8

用户 B：

Remix

得到：

My Website
Forked from A

之后两个网站完全独立。

12. 网站分享系统

每个网站都有：

Website ID
Owner ID
Version
Visibility

状态：

Private
Unlisted
Public
13. 社区系统

首页：

Explore

展示：

Trending
New
Popular
Most Remixed
Most Used

用户可以：

View

Use

Remix

Like

14. 部署架构
平台部署
Git / Build Artifact
        ↓
Container Registry
        ↓
Deployment Controller
        ↓
Kubernetes / Docker
自定义服务器

推荐：

Platform
    ↓
HTTPS
    ↓
Deployment API
    ↓
User Server Agent
    ↓
Docker Compose

不要让平台长期保存用户服务器 Root SSH 密钥。

15. Self-host Agent

用户服务器运行：

web-platform-agent

Agent：

拉取部署任务
验证签名
拉取镜像
启动容器
上报状态
获取日志

平台：

Create deployment
       ↓
Agent receives
       ↓
Verify signature
       ↓
Deploy
       ↓
Report status
16. Agent 不应该执行任意命令

不要：

{
  "command": "docker exec ..."
}

而是：

{
  "action": "DEPLOY",
  "image": "registry/app:abc123",
  "port": 3000
}

Agent 只有固定能力：

DEPLOY
START
STOP
RESTART
ROLLBACK
STATUS
LOGS
17. 数据库

推荐：

Platform

PostgreSQL

Generated Apps

默认：

PostgreSQL

数据库隔离：

Platform DB
     ≠
Application DB

不要让 AI 生成的网站直接访问平台数据库。

18. Storage

文件：

S3 Compatible

例如：

MinIO
Cloudflare R2
AWS S3

网站：

/upload

只能通过 Storage API 操作。

19. API

统一：

/api/v1

例如：

POST /api/v1/auth/login
GET  /api/v1/products
POST /api/v1/products
PUT  /api/v1/products/:id
DELETE /api/v1/products/:id
20. 权限

每个 Application 有：

Owner
Admin
Editor
User
Guest

AI 创建网站时自动生成：

Role
Permission
Resource
Action

例如：

product:create
product:update
product:delete
product:view
21. Tech Stack

如果按照你熟悉的开发方式：

Frontend
React
TypeScript
Vite
Ant Design
Tailwind
Framer Motion
Zustand
Backend

推荐：

Python
FastAPI
SQLAlchemy
PostgreSQL
Redis
Celery / Arq
AI

做成 Provider 抽象：

OpenAI
Anthropic
Gemini
Qwen
DeepSeek
用户自己的 API Key
22. Monorepo
platform/
│
├── apps/
│   ├── web/
│   ├── builder/
│   ├── admin/
│   └── runtime/
│
├── services/
│   ├── ai/
│   ├── builder/
│   ├── deployment/
│   ├── auth/
│   ├── storage/
│   └── billing/
│
├── packages/
│   ├── ui/
│   ├── schema/
│   ├── runtime/
│   ├── security/
│   └── sdk/
│
└── agent/
    └── deployment-agent/
23. 最重要的技术原则
AI 生成 Schema

↓

Schema 生成代码

↓

Code Build

↓

Automated Test

↓

Security Scan

↓

Deploy

而不是：

Prompt → AI → 直接上线