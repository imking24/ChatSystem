import os
import socket
import sys
import threading


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from common.protocol import recv_json, send_json


HOST = "127.0.0.1"
PORT = 9000
HEARTBEAT_INTERVAL = 10


def format_history_time(timestamp):
    """Format a SQLite timestamp for compact display."""
    if not timestamp:
        return ""
    return str(timestamp).replace("T", " ")[:16]


def print_history(messages):
    """Print history messages returned by the server."""
    if not messages:
        print("\n暂无历史消息")
        return

    for item in messages:
        timestamp = format_history_time(item.get("timestamp", ""))
        msg_type = item.get("msg_type")
        sender = item.get("sender", "")
        content = item.get("content", "")

        if msg_type == "private":
            receiver = item.get("receiver", "")
            print(f"\n[历史][私聊][{timestamp}][{sender} -> {receiver}] {content}")
        elif msg_type == "group":
            group = item.get("group_name", "")
            print(f"\n[历史][群聊][{timestamp}][{group}][{sender}] {content}")
        else:
            print(f"\n[历史][{timestamp}] {content}")


def receive_loop(sock, stop_event):
    """Continuously receive and print messages from the server."""
    while not stop_event.is_set():
        try:
            message = recv_json(sock)
        except (ConnectionResetError, OSError, ValueError) as exc:
            print(f"\n[client] receive error: {exc}")
            stop_event.set()
            break

        if message is None:
            print("\n[client] server closed the connection")
            stop_event.set()
            break

        msg_type = message.get("type")
        if msg_type == "system":
            print(f"\n[system] {message.get('content', '')}")
        elif msg_type == "chat":
            print(f"\n{message.get('content', '')}")
        elif msg_type == "private_msg":
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            print(f"\n[私聊][{sender}] {content}")
        elif msg_type == "group_msg":
            group = message.get("group", "unknown")
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            print(f"\n[群聊][{group}][{sender}] {content}")
        elif msg_type == "online_list":
            users = message.get("users", [])
            print(f"\n[online] {', '.join(users) if users else '当前没有在线用户'}")
        elif msg_type == "history":
            print_history(message.get("messages", []))
        elif msg_type == "message_sent":
            print(f"\n[system] 消息已发送，ID: {message.get('message_id')}")
        elif msg_type == "recall_notice":
            print(f"\n[撤回] {message.get('content', '有一条消息已撤回')}")
        elif msg_type == "error":
            print(f"\n[error] {message.get('content', '')}")
        else:
            print(f"\n[server] {message}")


def send_json_locked(sock, data, send_lock):
    """Send one JSON message without interleaving with heartbeat writes."""
    with send_lock:
        send_json(sock, data)


def heartbeat_loop(sock, stop_event, heartbeat_stop_event, send_lock):
    """Send heartbeat messages until the client exits."""
    while not stop_event.is_set() and not heartbeat_stop_event.wait(HEARTBEAT_INTERVAL):
        try:
            send_json_locked(sock, {"type": "heartbeat"}, send_lock)
        except OSError as exc:
            print(f"\n[client] heartbeat error: {exc}")
            stop_event.set()
            break


def login(sock):
    """Prompt for a username until the server accepts it."""
    while True:
        username = input("请输入用户名: ").strip()
        if not username:
            print("[client] 用户名不能为空")
            continue

        send_json(sock, {"type": "login", "username": username})
        response = recv_json(sock)
        if response is None:
            print("[client] server closed the connection")
            return False

        if response.get("type") == "login_success":
            print(f"[client] {response.get('content', '登录成功')}")
            return True

        if response.get("type") == "login_failed":
            print(f"[client] 登录失败: {response.get('content', '')}")
        else:
            print(f"[client] unexpected response: {response}")


def main():
    """Connect to the server and start the interactive chat client."""
    stop_event = threading.Event()
    heartbeat_stop_event = threading.Event()
    send_lock = threading.Lock()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
    except OSError as exc:
        print(f"[client] failed to connect to {HOST}:{PORT}: {exc}")
        return

    print(f"[client] connected to {HOST}:{PORT}")
    if not login(sock):
        sock.close()
        return

    print("[client] type messages and press Enter.")
    print("[client] commands: /msg <用户名> <消息内容>, /create_group <群名>, /join_group <群名>, /leave_group <群名>, /gmsg <群名> <消息内容>, /recall <消息ID>, /history, /online, /stop_heartbeat, /quit")

    receiver = threading.Thread(
        target=receive_loop,
        args=(sock, stop_event),
        daemon=True,
    )
    receiver.start()

    heartbeat = threading.Thread(
        target=heartbeat_loop,
        args=(sock, stop_event, heartbeat_stop_event, send_lock),
        daemon=True,
    )
    heartbeat.start()

    try:
        while not stop_event.is_set():
            text = input("> ").strip()
            if text == "/quit":
                send_json_locked(sock, {"type": "quit"}, send_lock)
                stop_event.set()
                break
            if text == "/online":
                send_json_locked(sock, {"type": "online_list"}, send_lock)
                continue
            if text == "/history":
                send_json_locked(sock, {"type": "history"}, send_lock)
                continue
            if text == "/recall":
                print("用法：/recall <消息ID>")
                continue
            if text.startswith("/recall "):
                parts = text.split(maxsplit=1)
                msg_id = parts[1].strip()
                if not msg_id:
                    print("用法：/recall <消息ID>")
                    continue
                send_json_locked(sock, {"type": "recall", "message_id": msg_id}, send_lock)
                continue
            if text == "/stop_heartbeat":
                heartbeat_stop_event.set()
                print("[client] heartbeat stopped for testing; socket remains open")
                continue
            if not text:
                continue
            if text == "/msg":
                print("用法：/msg <用户名> <消息内容>")
                continue
            if text.startswith("/msg "):
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    print("用法：/msg <用户名> <消息内容>")
                    continue
                send_json_locked(
                    sock,
                    {
                        "type": "private_msg",
                        "to": parts[1],
                        "content": parts[2],
                    },
                    send_lock,
                )
                continue
            if text == "/create_group":
                print("用法：/create_group <群名>")
                continue
            if text.startswith("/create_group "):
                parts = text.split(maxsplit=1)
                group_name = parts[1].strip()
                if not group_name:
                    print("用法：/create_group <群名>")
                    continue
                send_json_locked(sock, {"type": "group_create", "group": group_name}, send_lock)
                continue
            if text == "/join_group":
                print("用法：/join_group <群名>")
                continue
            if text.startswith("/join_group "):
                parts = text.split(maxsplit=1)
                group_name = parts[1].strip()
                if not group_name:
                    print("用法：/join_group <群名>")
                    continue
                send_json_locked(sock, {"type": "group_join", "group": group_name}, send_lock)
                continue
            if text == "/leave_group":
                print("用法：/leave_group <群名>")
                continue
            if text.startswith("/leave_group "):
                parts = text.split(maxsplit=1)
                group_name = parts[1].strip()
                if not group_name:
                    print("用法：/leave_group <群名>")
                    continue
                send_json_locked(sock, {"type": "group_leave", "group": group_name}, send_lock)
                continue
            if text == "/gmsg":
                print("用法：/gmsg <群名> <消息内容>")
                continue
            if text.startswith("/gmsg "):
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    print("用法：/gmsg <群名> <消息内容>")
                    continue
                send_json_locked(
                    sock,
                    {
                        "type": "group_msg",
                        "group": parts[1],
                        "content": parts[2],
                    },
                    send_lock,
                )
                continue

            send_json_locked(sock, {"type": "chat", "content": text}, send_lock)
    except (KeyboardInterrupt, EOFError):
        stop_event.set()
    except OSError as exc:
        print(f"[client] send error: {exc}")
        stop_event.set()
    finally:
        stop_event.set()
        heartbeat.join(timeout=1)
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        print("[client] bye")


if __name__ == "__main__":
    main()
