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


HOST = "127.0.0.1"
PORT = 9000
HEARTBEAT_CHECK_INTERVAL = 5
HEARTBEAT_TIMEOUT = 30

clients = []
online_users = {}
last_heartbeat = {}
groups = {}
clients_lock = threading.Lock()
db_manager = DBManager()


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
            last_heartbeat.pop(username, None)
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
    """Periodically remove users whose heartbeat has timed out."""
    while True:
        time.sleep(HEARTBEAT_CHECK_INTERVAL)
        now = time.time()

        with clients_lock:
            expired_users = [
                (username, online_users[username])
                for username, last_seen in list(last_heartbeat.items())
                if username in online_users and now - last_seen > HEARTBEAT_TIMEOUT
            ]

        for username, client_sock in expired_users:
            mark_user_offline(client_sock, username, "heartbeat timeout")


def login_client(client_sock):
    """Keep asking this connection for a unique username until login succeeds."""
    while True:
        message = recv_json(client_sock)
        if message is None:
            return None

        if message.get("type") != "login":
            send_json(
                client_sock,
                {"type": "login_failed", "content": "请先登录"},
            )
            continue

        username = str(message.get("username", "")).strip()
        if not username:
            send_json(
                client_sock,
                {"type": "login_failed", "content": "用户名不能为空"},
            )
            continue

        with clients_lock:
            if username in online_users:
                is_available = False
            else:
                online_users[username] = client_sock
                last_heartbeat[username] = time.time()
                is_available = True

        if not is_available:
            send_json(
                client_sock,
                {"type": "login_failed", "content": "用户名已在线"},
            )
            continue

        send_json(client_sock, {"type": "login_success", "content": "登录成功"})
        return username


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

    try:
        send_json(
            target_sock,
            {
                "type": "private_msg",
                "from": sender_name,
                "content": content,
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
    send_json(
        sender_sock,
        {
            "type": "system",
            "content": f"私聊消息已发送给 {target_name}",
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

    outgoing = {
        "type": "group_msg",
        "group": group_name,
        "from": username,
        "content": content,
    }
    disconnected = []
    for member_name, member_sock in targets:
        try:
            send_json(member_sock, outgoing)
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
                with clients_lock:
                    if online_users.get(username) is client_sock:
                        last_heartbeat[username] = time.time()
            elif msg_type == "chat":
                text = str(message.get("content", ""))
                outgoing = {
                    "type": "chat",
                    "content": f"[{username}] {text}",
                }
                print(f"[server] {username}: {text}")
                broadcast(outgoing)
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
