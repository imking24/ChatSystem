"""
client_network.py
Person2(King) 客户端网络层。

职责：
1. 连接/断开服务端
2. 注册、登录、心跳
3. 私聊/群聊文本发送
4. 历史记录请求
5. 消息撤回请求
6. 文件分块上传与接收保存
7. 接收线程与 UI 解耦

注意：
- 这里不直接操作数据库；数据库由 Person4 的服务端处理。
- UI 只调用本类方法，收到的数据通过 on_event 回调送回 UI。
"""

from __future__ import annotations

import base64
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from client_protocol import (
    MESSAGE_TYPE_REGISTER,
    MESSAGE_TYPE_LOGIN,
    MESSAGE_TYPE_LOGOUT,
    MESSAGE_TYPE_MESSAGE,
    MESSAGE_TYPE_HEARTBEAT,
    MESSAGE_TYPE_HISTORY_REQUEST,
    MESSAGE_TYPE_RECALL_REQUEST,
    MESSAGE_TYPE_ONLINE_LIST_REQUEST,
    MESSAGE_TYPE_GROUP_CREATE,
    MESSAGE_TYPE_GROUP_JOIN,
    MESSAGE_TYPE_GROUP_LEAVE,
    MESSAGE_TYPE_FILE_START,
    MESSAGE_TYPE_FILE_CHUNK,
    MESSAGE_TYPE_FILE_END,
    MESSAGE_TYPE_FILE_RECEIVED,
    now_iso,
    send_json,
    recv_json,
)


class ChatClientNetwork:
    def __init__(
        self,
        on_event: Callable[[dict], None],
        download_dir: str = "downloads",
        heartbeat_interval: int = 10,
        file_chunk_size: int = 32 * 1024,
    ):
        self.on_event = on_event
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

        self.heartbeat_interval = heartbeat_interval
        self.file_chunk_size = file_chunk_size

        self.sock: Optional[socket.socket] = None
        self.username: Optional[str] = None

        self._running = False
        self._send_lock = threading.Lock()
        self._recv_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

        # key = transfer_id 或 sender:filename
        self._incoming_files: dict[str, dict] = {}

    # --------------------
    # 连接管理
    # --------------------
    def connect(self, host: str, port: int, timeout: float = 5.0) -> None:
        if self.sock:
            self.disconnect()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.settimeout(None)

        self.sock = sock
        self._running = True

        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        self._emit({"type": "client_log", "message": f"已连接服务器 {host}:{port}"})

    def disconnect(self) -> None:
        self._running = False

        if self.sock:
            try:
                if self.username:
                    self.send({
                        "type": MESSAGE_TYPE_LOGOUT,
                        "sender": self.username,
                        "timestamp": now_iso(),
                    })
            except Exception:
                pass

            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

            try:
                self.sock.close()
            except Exception:
                pass

        self.sock = None
        self._emit({"type": "client_log", "message": "已断开连接"})

    def is_connected(self) -> bool:
        return self.sock is not None and self._running

    # --------------------
    # 统一发送
    # --------------------
    def send(self, obj: dict) -> None:
        if not self.sock:
            raise ConnectionError("尚未连接服务器")
        with self._send_lock:
            send_json(self.sock, obj)

    def _emit(self, event: dict) -> None:
        try:
            self.on_event(event)
        except Exception:
            pass

    # --------------------
    # 用户认证
    # --------------------
    def register(self, username: str, password: str) -> None:
        self.send({
            "type": MESSAGE_TYPE_REGISTER,
            "username": username,
            "password": password,
            "timestamp": now_iso(),
        })

    def login(self, username: str, password: str) -> None:
        # 先记录，若服务端返回失败，UI 可提示；收到成功后仍保持该用户名。
        self.username = username
        self.send({
            "type": MESSAGE_TYPE_LOGIN,
            "username": username,
            "password": password,
            "timestamp": now_iso(),
        })

    # --------------------
    # 聊天功能
    # --------------------
    def send_text(self, receiver: str, content: str, chat_type: str = "private") -> str:
        if not self.username:
            raise RuntimeError("请先登录")

        client_msg_id = str(uuid.uuid4())
        self.send({
            "type": MESSAGE_TYPE_MESSAGE,
            "sender": self.username,
            "receiver": receiver,
            "chat_type": chat_type,       # private/group，服务端可忽略，但 UI 需要
            "content": content,
            "client_msg_id": client_msg_id,
            "timestamp": now_iso(),
        })
        return client_msg_id

    def request_history(self, peer: str, count: int = 50) -> None:
        if not self.username:
            raise RuntimeError("请先登录")

        self.send({
            "type": MESSAGE_TYPE_HISTORY_REQUEST,
            "sender": self.username,
            "receiver": peer,
            "count": count,
            "timestamp": now_iso(),
        })

    def recall_message(self, msg_id: int | str) -> None:
        if not self.username:
            raise RuntimeError("请先登录")

        self.send({
            "type": MESSAGE_TYPE_RECALL_REQUEST,
            "sender": self.username,
            "msg_id": msg_id,
            "timestamp": now_iso(),
        })

    def request_online_list(self) -> None:
        if not self.username:
            raise RuntimeError("请先登录")

        self.send({
            "type": MESSAGE_TYPE_ONLINE_LIST_REQUEST,
            "sender": self.username,
            "timestamp": now_iso(),
        })

    # --------------------
    # 群组 UI 对接
    # --------------------
    def create_group(self, group_name: str) -> None:
        self._group_action(MESSAGE_TYPE_GROUP_CREATE, group_name)

    def join_group(self, group_name: str) -> None:
        self._group_action(MESSAGE_TYPE_GROUP_JOIN, group_name)

    def leave_group(self, group_name: str) -> None:
        self._group_action(MESSAGE_TYPE_GROUP_LEAVE, group_name)

    def _group_action(self, msg_type: str, group_name: str) -> None:
        if not self.username:
            raise RuntimeError("请先登录")
        self.send({
            "type": msg_type,
            "sender": self.username,
            "group": group_name,
            "timestamp": now_iso(),
        })

    # --------------------
    # 文件传输
    # --------------------
    def send_file(self, receiver: str, file_path: str, chat_type: str = "private") -> str:
        if not self.username:
            raise RuntimeError("请先登录")

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        file_size = path.stat().st_size
        total_chunks = (file_size + self.file_chunk_size - 1) // self.file_chunk_size
        transfer_id = str(uuid.uuid4())

        self.send({
            "type": MESSAGE_TYPE_FILE_START,
            "sender": self.username,
            "receiver": receiver,
            "chat_type": chat_type,
            "transfer_id": transfer_id,
            "filename": path.name,
            "file_size": file_size,
            "total_chunks": total_chunks,
            "timestamp": now_iso(),
        })

        with path.open("rb") as f:
            chunk_index = 0
            while True:
                chunk = f.read(self.file_chunk_size)
                if not chunk:
                    break

                self.send({
                    "type": MESSAGE_TYPE_FILE_CHUNK,
                    "sender": self.username,
                    "receiver": receiver,
                    "chat_type": chat_type,
                    "transfer_id": transfer_id,
                    "filename": path.name,
                    "chunk_index": chunk_index,
                    "chunk_data": base64.b64encode(chunk).decode("ascii"),
                    "timestamp": now_iso(),
                })

                chunk_index += 1
                self._emit({
                    "type": "file_send_progress",
                    "filename": path.name,
                    "sent_chunks": chunk_index,
                    "total_chunks": total_chunks,
                })

        self.send({
            "type": MESSAGE_TYPE_FILE_END,
            "sender": self.username,
            "receiver": receiver,
            "chat_type": chat_type,
            "transfer_id": transfer_id,
            "filename": path.name,
            "timestamp": now_iso(),
        })

        return transfer_id

    def _handle_file_event(self, data: dict) -> bool:
        msg_type = data.get("type")
        if msg_type not in {MESSAGE_TYPE_FILE_START, MESSAGE_TYPE_FILE_CHUNK, MESSAGE_TYPE_FILE_END}:
            return False

        sender = data.get("sender", "unknown")
        filename = os.path.basename(data.get("filename", "unknown_file"))
        transfer_id = data.get("transfer_id") or f"{sender}:{filename}"

        if msg_type == MESSAGE_TYPE_FILE_START:
            self._incoming_files[transfer_id] = {
                "sender": sender,
                "filename": filename,
                "file_size": data.get("file_size", 0),
                "total_chunks": data.get("total_chunks", 0),
                "chunks": {},
            }
            self._emit({
                "type": "client_log",
                "message": f"开始接收文件：{filename}，来自 {sender}",
            })
            return True

        if msg_type == MESSAGE_TYPE_FILE_CHUNK:
            info = self._incoming_files.setdefault(transfer_id, {
                "sender": sender,
                "filename": filename,
                "file_size": 0,
                "total_chunks": 0,
                "chunks": {},
            })
            idx = int(data.get("chunk_index", 0))
            raw = base64.b64decode(data.get("chunk_data", ""))
            info["chunks"][idx] = raw
            self._emit({
                "type": "file_recv_progress",
                "filename": filename,
                "received_chunks": len(info["chunks"]),
                "total_chunks": info.get("total_chunks", 0),
            })
            return True

        if msg_type == MESSAGE_TYPE_FILE_END:
            info = self._incoming_files.pop(transfer_id, None)
            if not info:
                self._emit({
                    "type": "client_error",
                    "message": f"文件结束包异常：{filename}",
                })
                return True

            safe_name = self._dedup_filename(info["filename"])
            out_path = self.download_dir / safe_name
            with out_path.open("wb") as f:
                for idx in sorted(info["chunks"].keys()):
                    f.write(info["chunks"][idx])

            self._emit({
                "type": MESSAGE_TYPE_FILE_RECEIVED,
                "sender": info["sender"],
                "filename": info["filename"],
                "saved_path": str(out_path.resolve()),
            })
            return True

        return False

    def _dedup_filename(self, filename: str) -> str:
        path = self.download_dir / filename
        if not path.exists():
            return filename
        stem = path.stem
        suffix = path.suffix
        for i in range(1, 10000):
            candidate = f"{stem}_{i}{suffix}"
            if not (self.download_dir / candidate).exists():
                return candidate
        return f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"

    # --------------------
    # 后台线程
    # --------------------
    def _recv_loop(self) -> None:
        while self._running and self.sock:
            try:
                data = recv_json(self.sock)
                if self._handle_file_event(data):
                    continue
                self._emit(data)
            except Exception as e:
                if self._running:
                    self._emit({"type": "client_error", "message": f"接收失败：{e}"})
                self._running = False
                break

    def _heartbeat_loop(self) -> None:
        while self._running:
            time.sleep(self.heartbeat_interval)
            if not self._running or not self.sock or not self.username:
                continue
            try:
                self.send({
                    "type": MESSAGE_TYPE_HEARTBEAT,
                    "sender": self.username,
                    "timestamp": now_iso(),
                })
            except Exception as e:
                self._emit({"type": "client_error", "message": f"心跳发送失败：{e}"})
                self._running = False
                break
