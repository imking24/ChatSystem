"""
client_protocol.py
Person2(King) 客户端侧协议定义与 TCP 粘包处理工具。

与 Person4 已有 protocol.py / DBManager / HistoryManager 对接要点：
- 普通聊天消息必须包含 type/sender/receiver/content/timestamp
- 文件开始消息必须包含 type/sender/receiver/filename/file_size/timestamp
- 客户端与服务端推荐统一使用：4 字节大端长度头 + JSON Body
"""

import json
import socket
import struct
from datetime import datetime, timezone

# 基础消息
MESSAGE_TYPE_REGISTER = "register"
MESSAGE_TYPE_LOGIN = "login"
MESSAGE_TYPE_LOGOUT = "logout"
MESSAGE_TYPE_MESSAGE = "message"
MESSAGE_TYPE_HEARTBEAT = "heartbeat"
MESSAGE_TYPE_RESPONSE = "response"

# 历史与撤回
MESSAGE_TYPE_HISTORY_REQUEST = "history_request"
MESSAGE_TYPE_HISTORY_RESPONSE = "history_response"
MESSAGE_TYPE_RECALL_REQUEST = "recall_request"
MESSAGE_TYPE_RECALL_NOTICE = "recall_notice"

# 在线状态
MESSAGE_TYPE_ONLINE_LIST_REQUEST = "online_list_request"
MESSAGE_TYPE_ONLINE_LIST = "online_list"

# 群组
MESSAGE_TYPE_GROUP_CREATE = "group_create"
MESSAGE_TYPE_GROUP_JOIN = "group_join"
MESSAGE_TYPE_GROUP_LEAVE = "group_leave"

# 文件传输
MESSAGE_TYPE_FILE_START = "file_start"
MESSAGE_TYPE_FILE_CHUNK = "file_chunk"
MESSAGE_TYPE_FILE_END = "file_end"
MESSAGE_TYPE_FILE_RECEIVED = "file_received"

HEADER_SIZE = 4


def now_iso() -> str:
    """返回 UTC ISO 时间，兼容数据库中的 timestamp 字段。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recvall(sock: socket.socket, n: int) -> bytes:
    """精确读取 n 字节，解决 TCP 粘包/半包问题。"""
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("连接已断开")
        data.extend(chunk)
    return bytes(data)


def send_json(sock: socket.socket, obj: dict) -> None:
    """发送 JSON：4 字节长度头 + JSON Body。"""
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    header = struct.pack("!I", len(body))
    sock.sendall(header + body)


def recv_json(sock: socket.socket) -> dict:
    """接收 JSON：先读 4 字节长度，再按长度读完整 Body。"""
    header = recvall(sock, HEADER_SIZE)
    length = struct.unpack("!I", header)[0]
    if length <= 0:
        raise ValueError("收到非法 JSON 长度")
    body = recvall(sock, length)
    return json.loads(body.decode("utf-8"))
