# ChatSystem 用户使用指南

## 1. 项目简介

ChatSystem 是一个基于 Python 的即时聊天系统，当前提供 TCP 聊天服务端、命令行客户端和 Tkinter 图形界面客户端。系统支持用户登录、在线用户列表、私聊、群聊、历史消息、消息撤回、心跳检测，以及群聊中的 `@AI` 助手能力。

服务端默认监听：

```text
127.0.0.1:9000
```

## 2. 项目结构

当前项目结构保留原样，主要文件与目录如下：

```text
ChatSystem/
├── startall.bat                  # Windows 一键启动脚本
├── ChatSystem_UserGuide.md       # 用户使用指南
├── README.md                     # 项目说明
├── client_gui.py                 # 图形界面客户端入口
├── client_network.py             # 旧版/辅助客户端网络模块
├── client_protocol.py            # 旧版/辅助客户端协议模块
├── message.py                    # 旧版/辅助消息模型
├── common/
│   └── protocol.py               # JSON Lines 协议收发工具
├── client/
│   └── client.py                 # 命令行客户端入口
├── server/
│   ├── server.py                 # TCP 服务端入口
│   ├── llm_client.py             # DeepSeek/OpenAI 兼容 AI 调用模块
│   ├── database/
│   │   ├── db_manager.py         # SQLite 数据库管理
│   │   └── chat_system.db        # 本地聊天数据库
│   ├── message/
│   │   └── history_manager.py    # 历史消息相关模块
│   └── user/
│       ├── session_manager.py    # 会话管理模块
│       └── user_handler.py       # 用户处理模块
├── tests/
│   └── stress_test.py            # 压力测试脚本
└── docs/
    └── screenshots/              # 项目截图
```

## 3. 环境准备

### 3.1 基础环境

- Python 3.7 或以上版本。
- Windows 用户建议使用 PowerShell 或 CMD。
- 图形界面客户端依赖 `tkinter`，通常随 Python 一起安装。
- 核心聊天功能主要使用 Python 标准库，不需要额外安装依赖。

### 3.2 AI 助手可选配置

如果需要在群聊中使用 `@AI`，需要安装 OpenAI 兼容 SDK：

```bash
python -m pip install openai
```

然后在项目根目录创建 `.env` 文件，填写：

```env
DEEPSEEK_API_KEY=你的 API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

其中 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 可以不填，系统会使用默认值。没有配置 API Key 时，普通聊天功能仍可正常使用，只有 `@AI` 回复不可用。

## 4. 启动方式

请先进入项目根目录：

```bash
cd C:\Users\LENOVO\Desktop\ChatSystem
```

### 4.1 一键启动：startall

Windows 下可以直接运行：

```bat
.\startall.bat
```

该脚本会自动完成两件事：

1. 在一个新窗口启动服务端：`python server\server.py`
2. 在另一个新窗口启动图形界面客户端：`python client_gui.py`

启动后，在图形界面中点击“连接”，再输入用户名并点击“登录”即可开始使用。

### 4.2 手动启动图形界面客户端

如果不使用 `startall`，可以手动打开两个终端。

第一个终端启动服务端：

```bash
python server/server.py
```

第二个终端启动图形界面客户端：

```bash
python client_gui.py
```

### 4.3 手动启动命令行客户端

第一个终端启动服务端：

```bash
python server/server.py
```

第二个或更多终端启动命令行客户端：

```bash
python client/client.py
```

命令行客户端连接成功后，按提示输入用户名登录。

## 5. 图形界面客户端使用说明

### 5.1 连接与登录

1. 服务器 IP 默认填写 `127.0.0.1`。
2. 端口默认填写 `9000`。
3. 点击“连接”。
4. 输入用户名。
5. 点击“登录”。

当前服务端使用用户名直接登录，用户名必须唯一。界面中的密码和注册入口已预留给后续扩展，当前服务端暂未处理注册消息。

### 5.2 私聊

1. 在“目标”中输入对方用户名，或在在线用户列表中双击用户。
2. 选择“私聊”。
3. 输入消息内容。
4. 点击“发送”或按 Enter。

### 5.3 群聊

1. 在左侧“群名”输入群名。
2. 点击“建群”创建群组。
3. 点击“入群”加入群组。
4. 在“目标”中填写群名。
5. 选择“群聊”。
6. 输入消息后发送。

退出群组时，在“群名”输入群名并点击“退群”。

### 5.4 历史消息

点击“拉取历史”可以查看最近 20 条相关历史消息，包括：

- 当前用户参与的私聊消息。
- 当前用户已加入群组中的群聊消息。

### 5.5 消息撤回

发送成功后，服务端会返回消息 ID。点击“撤回上一条”可以撤回最近发送的一条消息。

撤回限制：

- 只能撤回自己发送的消息。
- 只能撤回发送后 2 分钟内的消息。
- 已撤回的消息不能重复撤回。

### 5.6 `@AI` 助手

`@AI` 当前在群聊中使用。操作方式：

1. 先创建或加入一个群组。
2. 切换到“群聊”。
3. 在“目标”中填写群名。
4. 输入问题。
5. 点击 `@AI` 按钮。

客户端会自动发送形如 `@AI 你的问题` 的群聊消息。服务端收到后会调用 AI 模块，并把回复发送回该群组。

## 6. 命令行客户端命令

命令行客户端支持以下命令：

```text
/online
```

查看当前在线用户。

```text
/msg <用户名> <消息内容>
```

发送一对一私聊消息。

```text
/create_group <群名>
```

创建群组。

```text
/join_group <群名>
```

加入群组。

```text
/leave_group <群名>
```

退出群组。

```text
/gmsg <群名> <消息内容>
```

发送群聊消息。

```text
/recall <消息ID>
```

撤回指定消息。

```text
/history
```

查看最近 20 条相关历史消息。

```text
/stop_heartbeat
```

停止当前客户端继续发送心跳，仅用于测试心跳超时机制。

```text
/quit
```

退出客户端。

普通文本会作为公共聊天消息发送给所有在线用户。

## 7. 停止系统

### 7.1 停止客户端

- 图形界面客户端：直接关闭窗口。
- 命令行客户端：输入 `/quit`，或按 `Ctrl+C`。

### 7.2 停止服务端

在服务端终端中按：

```text
Ctrl+C
```

## 8. 压力测试

先启动服务端：

```bash
python server/server.py
```

再打开另一个终端运行：

```bash
python tests/stress_test.py
```

压力测试会模拟多个客户端连接、登录、发送消息、请求在线列表并退出，用于验证服务端稳定性。

## 9. 常见问题

### Q1：客户端连接失败怎么办？

请确认服务端已经启动，并且监听地址是 `127.0.0.1:9000`。如果端口被占用，请先关闭占用该端口的旧服务端进程。

### Q2：登录失败提示用户名已在线怎么办？

同一时间不能有两个客户端使用同一个用户名。请换一个用户名，或关闭原来的客户端后等待服务端清理连接。

### Q3：`@AI` 没有回复怎么办？

请确认已经安装 `openai` 包，并在项目根目录 `.env` 中配置了 `DEEPSEEK_API_KEY`。如果没有配置，普通聊天功能不受影响。

### Q4：历史消息在哪里保存？

历史消息保存在本地 SQLite 数据库：

```text
server/database/chat_system.db
```

### Q5：`startall` 启动后为什么有多个窗口？

这是正常现象。`startall.bat` 会把服务端和图形界面客户端分别放到独立窗口中，方便观察服务端日志并独立操作客户端。

## 10. 联系与反馈

如在使用过程中遇到问题或有改进建议，可以通过以下邮箱反馈：

```text
arrie.wyzzz@sjtu.edu.cn
```
