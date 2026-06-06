import os
import socket
import sys
import threading
import time


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from common.protocol import recv_json, send_json
from server.database.db_manager import DBManager
from server.user.session_manager import SessionManager
from server.user.user_handler import UserHandler
from server.message.history_manager import HistoryManager


HOST = "127.0.0.1"
PORT = 9000
HEARTBEAT_CHECK_INTERVAL = 5
HEARTBEAT_TIMEOUT = 30
RECALL_LIMIT = 120

clients = []
online_users = {}
groups = {}
recent_messages = {}

clients_lock = threading.Lock()
db_manager = DBManager()
user_handler = UserHandler()
session_manager = SessionManager()
history_manager = HistoryManager()


def broadcast(message, exclude_sock=None):
    """Send a message to every logged-in client."""
    disconnected = []

    with clients_lock:
        current_clients = list(online_users.values())

    for client_sock in current_clients:
        if client_sock is exclude_sock:
            continue

        try:
            send_json(client_sock, message)
        except OSError:
            disconnected.append(client_sock)

    for client_sock in disconnected:
        remove_client(client_sock)


def remove_client(client_sock, username=None):
    """Remove and close a client socket if it is still registered."""
    removed_username = None

    with clients_lock:
        if client_sock in clients:
            clients.remove(client_sock)
        if username is None:
            for current_username, current_sock in list(online_users.items()):
                if current_sock is client_sock:
                    username = current_username
                    break
        if username and online_users.get(username) is client_sock:
            del online_users[username]
            removed_username = username
        if username:
            for members in groups.values():
                members.discard(username)

    try:
        client_sock.close()
    except OSError:
        pass

    return removed_username


def mark_user_offline(client_sock, username, reason):
    """Remove one online user and broadcast a single offline notice."""
    removed_username = remove_client(client_sock, username)
    if removed_username:
        print(f"[server] user offline: {removed_username} ({reason})")
        broadcast(
            {
                "type": "system",
                "content": f"{removed_username} 已离线",
            }
        )


def heartbeat_monitor():
    """Periodically remove users whose heartbeat has timed out, and clean up expired messages."""
    while True:
        time.sleep(HEARTBEAT_CHECK_INTERVAL)
        now = time.time()

        # 使用 SessionManager 检查超时用户
        session_manager.check_dead_sessions()
        
        # 同步 SessionManager 的超时用户到 online_users
        with clients_lock:
            active_users = set(session_manager.active_sessions.keys())
            offline_users = []
            offline_users_to_remove = []  # 在这里定义！
            
            for username in list(online_users.keys()):
                if username not in active_users:
                    offline_users.append(username)
            
            for username in offline_users:
                client_sock = online_users.get(username)
                if client_sock:
                    offline_users_to_remove.append((username, client_sock))
        
        for username, client_sock in offline_users_to_remove:
            mark_user_offline(client_sock, username, "heartbeat timeout")

        # 清理过期的撤回消息
        with clients_lock:
            expired_msg_ids = [
                msg_id for msg_id, info in recent_messages.items()
                if now - info["time"] > RECALL_LIMIT
            ]
            for msg_id in expired_msg_ids:
                recent_messages.pop(msg_id, None)


def handle_register(client_sock, message):
    """处理用户注册请求"""
    result = user_handler.handle_register(message)
    
    if result["status"] == "success":
        send_json(client_sock, {
            "type": "register_success",
            "content": result["message"]
        })
    else:
        send_json(client_sock, {
            "type": "register_failed",
            "content": result["message"]
        })


def handle_login(client_sock, message):
    """处理用户登录请求（带密码验证）"""
    username = message.get("username", "").strip()
    password = message.get("password", "").strip()
    
    # 调用 UserHandler 验证登录
    result = user_handler.handle_login({"username": username, "password": password})
    
    if result["status"] != "success":
        send_json(client_sock, {
            "type": "login_failed",
            "content": result["message"]
        })
        return None
    
    # 检查是否已经在线
    with clients_lock:
        if username in online_users:
            send_json(client_sock, {
                "type": "login_failed",
                "content": "用户已在其他客户端登录"
            })
            return None
        
        # 登录成功，添加到在线列表
        online_users[username] = client_sock
    
    # 更新会话管理器的心跳
    session_manager.update_heartbeat(username)
    
    send_json(client_sock, {
        "type": "login_success",
        "content": f"登录成功，欢迎 {username}"
    })
    
    return username


def login_client(client_sock):
    """处理客户端的登录/注册流程"""
    while True:
        message = recv_json(client_sock)
        if message is None:
            return None
        
        msg_type = message.get("type")
        
        if msg_type == "register":
            handle_register(client_sock, message)
            continue
        
        elif msg_type == "login":
            username = handle_login(client_sock, message)
            if username:
                return username
            continue
        
        else:
            send_json(
                client_sock,
                {"type": "login_failed", "content": "请先注册或登录"},
            )


def handle_private_message(sender_sock, sender_name, message):
    """Send a private message to one online user."""
    target_name = str(message.get("to", "")).strip()
    content = str(message.get("content", ""))

    with clients_lock:
        target_sock = online_users.get(target_name)

    if target_sock is None:
        send_json(
            sender_sock,
            {"type": "error", "content": f"用户 {target_name} 不在线"},
        )
        return

    msg_id = str(time.time_ns())
    with clients_lock:
        recent_messages[msg_id] = {
            "sender": sender_name,
            "time": time.time(),
            "type": "private",
            "target": [sender_name, target_name],
            "content": content
        }

    # 发送给接收方（带 _msg_id）
    try:
        send_json(
            target_sock,
            {
                "type": "private_msg",
                "from": sender_name,
                "content": content,
                "_msg_id": msg_id,
            },
        )
    except OSError:
        remove_client(target_sock, target_name)
        send_json(
            sender_sock,
            {"type": "error", "content": f"用户 {target_name} 不在线"},
        )
        return

    db_manager.save_private_message(sender_name, target_name, content)
    
    # 发送给发送方（带 msg_id，显示）
    send_json(
        sender_sock,
        {
            "type": "private_msg",
            "from": sender_name,
            "content": content,
            "msg_id": msg_id,
        },
    )


def handle_group_create(client_sock, username, message):
    """Create a group and add the creator to it."""
    group_name = str(message.get("group", "")).strip()
    if not group_name:
        send_json(client_sock, {"type": "error", "content": "群名不能为空"})
        return

    with clients_lock:
        if group_name in groups:
            exists = True
        else:
            groups[group_name] = {username}
            exists = False

    if exists:
        send_json(client_sock, {"type": "error", "content": f"群组 {group_name} 已存在"})
        return

    send_json(client_sock, {"type": "system", "content": f"群组 {group_name} 创建成功"})


def handle_group_join(client_sock, username, message):
    """Join an existing group."""
    group_name = str(message.get("group", "")).strip()
    if not group_name:
        send_json(client_sock, {"type": "error", "content": "群名不能为空"})
        return

    with clients_lock:
        members = groups.get(group_name)
        if members is None:
            status = "missing"
        elif username in members:
            status = "already_joined"
        else:
            members.add(username)
            status = "joined"

    if status == "missing":
        send_json(client_sock, {"type": "error", "content": f"群组 {group_name} 不存在"})
    elif status == "already_joined":
        send_json(client_sock, {"type": "system", "content": "你已在该群组中"})
    else:
        send_json(client_sock, {"type": "system", "content": f"已加入群组 {group_name}"})


def handle_group_leave(client_sock, username, message):
    """Leave a group."""
    group_name = str(message.get("group", "")).strip()
    if not group_name:
        send_json(client_sock, {"type": "error", "content": "群名不能为空"})
        return

    with clients_lock:
        members = groups.get(group_name)
        if members is None or username not in members:
            in_group = False
        else:
            members.remove(username)
            in_group = True

    if not in_group:
        send_json(client_sock, {"type": "error", "content": f"你不在群组 {group_name} 中"})
        return

    send_json(client_sock, {"type": "system", "content": f"已退出群组 {group_name}"})


def handle_group_message(client_sock, username, message):
    """Send a chat message to online members of one group."""
    group_name = str(message.get("group", "")).strip()
    content = str(message.get("content", ""))
    if not group_name:
        send_json(client_sock, {"type": "error", "content": "群名不能为空"})
        return

    with clients_lock:
        members = groups.get(group_name)
        if members is None:
            status = "missing"
            targets = []
        elif username not in members:
            status = "not_member"
            targets = []
        else:
            status = "ok"
            targets = [
                (member_name, online_users[member_name])
                for member_name in list(members)
                if member_name in online_users
            ]

    if status == "missing":
        send_json(client_sock, {"type": "error", "content": f"群组 {group_name} 不存在"})
        return
    if status == "not_member":
        send_json(client_sock, {"type": "error", "content": f"你不在群组 {group_name} 中"})
        return

    msg_id = str(time.time_ns())
    with clients_lock:
        recent_messages[msg_id] = {
            "sender": username,
            "time": time.time(),
            "type": "group",
            "target": group_name,
            "content": content
        }

    disconnected = []
    for member_name, member_sock in targets:
        try:
            if member_name == username:
                send_json(member_sock, {
                    "type": "group_msg",
                    "group": group_name,
                    "from": username,
                    "content": content,
                    "msg_id": msg_id,
                })
            else:
                send_json(member_sock, {
                    "type": "group_msg",
                    "group": group_name,
                    "from": username,
                    "content": content,
                    "_msg_id": msg_id,
                })
        except OSError:
            disconnected.append((member_sock, member_name))

    for member_sock, member_name in disconnected:
        remove_client(member_sock, member_name)

    db_manager.save_group_message(username, group_name, content)


def handle_history(client_sock, username):
    """Return recent private messages and messages from groups the user is in."""
    with clients_lock:
        user_groups = [
            group_name
            for group_name, members in groups.items()
            if username in members
        ]

    history = db_manager.get_recent_history(username, user_groups, limit=20)
    send_json(client_sock, {"type": "history", "messages": history})


def handle_recall_request(client_sock, username, message):
    """Handle message recall request with a 2-minute limit."""
    msg_id = str(message.get("msg_id", "")).strip()

    with clients_lock:
        msg_info = recent_messages.get(msg_id)

    if not msg_info:
        send_json(client_sock, {"type": "error", "content": "消息不存在或已超过2分钟无法撤回"})
        return

    if msg_info["sender"] != username:
        send_json(client_sock, {"type": "error", "content": "无权撤回他人发送的消息"})
        return

    time_diff = time.time() - msg_info["time"]
    if time_diff > RECALL_LIMIT:
        send_json(client_sock, {"type": "error", "content": "消息发送已超过2分钟，撤回失败"})
        return

    with clients_lock:
        recent_messages.pop(msg_id, None)

    print(f"[server] message recalled by {username}, msg_id: {msg_id}")

    recall_notice = {
        "type": "recall",
        "msg_id": msg_id,
        "sender": username,
    }

    # 根据消息类型广播给相关用户
    if msg_info["type"] == "chat":
        broadcast(recall_notice)
    elif msg_info["type"] == "private":
        with clients_lock:
            for user in msg_info["target"]:
                sock = online_users.get(user)
                if sock:
                    try:
                        send_json(sock, recall_notice)
                    except OSError:
                        pass
    elif msg_info["type"] == "group":
        group_name = msg_info["target"]
        with clients_lock:
            members = list(groups.get(group_name, set()))
            for member_name in members:
                sock = online_users.get(member_name)
                if sock:
                    try:
                        send_json(sock, recall_notice)
                    except OSError:
                        pass

    send_json(client_sock, {"type": "system", "content": "消息撤回成功"})


def handle_client(client_sock, address):
    """Handle one connected client in its own thread."""
    print(f"[server] client connected: {address}")
    username = None

    try:
        username = login_client(client_sock)
        if username is None:
            return

        print(f"[server] user logged in: {username}")
        broadcast(
            {
                "type": "system",
                "content": f"{username} 加入聊天室",
            },
            exclude_sock=client_sock,
        )

        while True:
            message = recv_json(client_sock)
            if message is None:
                break

            msg_type = message.get("type")

            if msg_type == "heartbeat":
                # 使用 SessionManager 更新心跳
                session_manager.update_heartbeat(username)
                
            elif msg_type == "chat":
                text = str(message.get("content", ""))
                
                msg_id = str(time.time_ns())
                with clients_lock:
                    recent_messages[msg_id] = {
                        "sender": username,
                        "time": time.time(),
                        "type": "chat",
                        "target": None,
                        "content": text
                    }
                
                print(f"[server] {username}: {text}")
                
                for other_sock in list(online_users.values()):
                    try:
                        if other_sock == client_sock:
                            send_json(other_sock, {
                                "type": "chat",
                                "content": f"[{username}] {text}",
                                "msg_id": msg_id,
                            })
                        else:
                            send_json(other_sock, {
                                "type": "chat",
                                "content": f"[{username}] {text}",
                                "_msg_id": msg_id,
                            })
                    except OSError:
                        pass
                            
            elif msg_type == "private_msg":
                handle_private_message(client_sock, username, message)
            elif msg_type == "group_create":
                handle_group_create(client_sock, username, message)
            elif msg_type == "group_join":
                handle_group_join(client_sock, username, message)
            elif msg_type == "group_leave":
                handle_group_leave(client_sock, username, message)
            elif msg_type == "group_msg":
                handle_group_message(client_sock, username, message)
            elif msg_type == "history":
                handle_history(client_sock, username)
            elif msg_type == "recall_request":
                handle_recall_request(client_sock, username, message)
            elif msg_type == "online_list":
                with clients_lock:
                    users = sorted(online_users.keys())
                send_json(client_sock, {"type": "online_list", "users": users})
            elif msg_type == "quit":
                break
            else:
                send_json(
                    client_sock,
                    {"type": "system", "content": "未知命令或消息类型"},
                )
    except (ConnectionResetError, OSError, ValueError) as exc:
        print(f"[server] client error {address}: {exc}")
    finally:
        removed_username = remove_client(client_sock, username)
        print(f"[server] client disconnected: {address}")
        if removed_username:
            broadcast(
                {
                    "type": "system",
                    "content": f"{removed_username} 已离线",
                }
            )


def main():
    """Start the TCP chat server."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen()

    print(f"[server] listening on {HOST}:{PORT}")

    monitor_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
    monitor_thread.start()

    try:
        while True:
            client_sock, address = server_sock.accept()
            with clients_lock:
                clients.append(client_sock)

            thread = threading.Thread(
                target=handle_client,
                args=(client_sock, address),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        with clients_lock:
            current_clients = list(clients)
            clients.clear()

        for client_sock in current_clients:
            try:
                client_sock.close()
            except OSError:
                pass

        server_sock.close()


if __name__ == "__main__":
    main()
