# ChatSystem - zy的任务
-数据库表设计与初始化
-用户认证系统（含验证码）
-会话管理与心跳检测
-消息存储与查询接口

## 1. 数据库管理 (`server/database/`)
- **文件**: `db_manager.py`
- **功能**: 
  -自动初始化 SQLite 数据库，创建 `users` 和 `messages` 表结构。
  -用户注册登录状态管理模块
  -消息存储与撤回模块


