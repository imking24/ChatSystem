#该文件为协议定义

#消息类型定义
MESSAGE_TYPE_LOGIN = "login"
MESSAGE_TYPE_LOGOUT = "logout"
MESSAGE_TYPE_MESSAGE = "message"#普通消息
MESSAGE_TYPE_HEARTBEAT = "heartbeat"#心跳机制标志
MESSAGE_TYPE_FILE_START = "file_start" # 文件传输开始
MESSAGE_TYPE_FILE_CHUNK = "file_chunk" # 文件分块
MESSAGE_TYPE_FILE_END = "file_end"     # 文件结束
MESSAGE_TYPE_RESPONSE = "response"     # 响应


#JSON消息格式规范
"""
基础消息格式：
{
  "type": "message/heartbeat/...",
  "sender": "user_id",
  "timestamp": "2026-04-17T12:00:00Z"
}

普通消息：
{
  "type": "message",
  "sender": "user123",
  "receiver": "user456",  // 可以是个人 ID 或群组 ID
  "content": "Hello world",
  "timestamp": "2026-04-17T12:00:00Z"
}

文件传输：
{
  "type": "file_start",
  "sender": "user123",
  "receiver": "user456",
  "filename": "document.pdf",
  "file_size": 1024000,
  "total_chunks": 100,
  "timestamp": "2026-04-17T12:00:00Z"
}

{文件分块
  "type": "file_chunk",
  "sender": "user123",
  "receiver": "user456",
  "filename": "document.pdf",
  "chunk_index": 0,
  "chunk_data": "base64_encoded_chunk",
  "timestamp": "2026-04-17T12:00:00Z"
}

{文件结束
  "type": "file_end",
  "sender": "user123",
  "receiver": "user456",
  "filename": "document.pdf",
  "timestamp": "2026-04-17T12:00:00Z"
}

心跳包：
{
  "type": "heartbeat",
  "sender": "user123",
  "timestamp": "2026-04-17T12:00:00Z"
}

响应：
{
  "type": "response",
  "status": "success/error",
  "message": "..."
}
"""

