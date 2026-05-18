import os
import socket
import sys
import threading
import getpass


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from common.protocol import recv_json, send_json


HOST = "127.0.0.1"
PORT = 9000
HEARTBEAT_INTERVAL = 10

# 全局变量
message_map = {}  # {msg_id: sender}
current_username = ""


def format_history_time(timestamp):
    if not timestamp:
        return ""
    return str(timestamp).replace("T", " ")[:16]


def print_history(messages):
    if not messages:
        print("\n暂无历史消息")
        return

    for item in messages:
        timestamp = format_history_time(item.get("timestamp", ""))
        msg_type = item.get("msg_type", "")
        sender = item.get("sender", "")
        content = item.get("content", "")
        msg_id = item.get("msg_id", "")
        show_id = (sender == current_username)
        id_prefix = f"[ID: {msg_id}] " if show_id and msg_id else ""

        if msg_type == "private":
            receiver = item.get("receiver", "")
            print(f"\n[历史][私聊]{id_prefix}[{timestamp}][{sender} -> {receiver}] {content}")
        elif msg_type == "group":
            group = item.get("group_name", "")
            print(f"\n[历史][群聊]{id_prefix}[{timestamp}][{group}][{sender}] {content}")
        else:
            print(f"\n[历史]{id_prefix}[{timestamp}] {content}")


def receive_loop(sock, stop_event):
    global message_map, current_username
    
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
        
        msg_id = message.get("msg_id") or message.get("_msg_id")
        msg_sender = message.get("from") or message.get("sender")
        
        if msg_id and msg_sender:
            message_map[msg_id] = msg_sender
        
        show_id = False
        if msg_id and message.get("msg_id"):
            if msg_sender == current_username:
                show_id = True
        
        id_prefix = f"[ID: {msg_id}] " if show_id else ""

        if msg_type == "system":
            print(f"\n[system] {message.get('content', '')}")
        elif msg_type == "error":
            print(f"\n[error] {message.get('content', '')}")
        elif msg_type == "register_success":
            print(f"\n[系统] {message.get('content', '注册成功')}")
        elif msg_type == "register_failed":
            print(f"\n[错误] {message.get('content', '注册失败')}")
        elif msg_type == "login_success":
            print(f"\n[系统] {message.get('content', '登录成功')}")
        elif msg_type == "login_failed":
            print(f"\n[错误] {message.get('content', '登录失败')}")
        elif msg_type == "chat":
            print(f"\n{id_prefix}{message.get('content', '')}")
        elif msg_type == "private_msg":
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            print(f"\n[私聊]{id_prefix}[{sender}] {content}")
        elif msg_type == "group_msg":
            group = message.get("group", "unknown")
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            print(f"\n[群聊][{group}]{id_prefix}[{sender}] {content}")
        elif msg_type == "online_list":
            users = message.get("users", [])
            print(f"\n[online] {', '.join(users) if users else '当前没有在线用户'}")
        elif msg_type == "history":
            print_history(message.get("messages", []))
        elif msg_type == "recall":
            sender = message.get("sender", "未知用户")
            recalled_id = message.get("msg_id", "未知")
            print(f"\n【撤回提示】: 用户 {sender} 撤回了消息 (ID: {recalled_id})")
            # 控制台版本无法删除已打印的消息
        else:
            print(f"\n[server] {message}")


def send_json_locked(sock, data, send_lock):
    with send_lock:
        send_json(sock, data)


def heartbeat_loop(sock, stop_event, heartbeat_stop_event, send_lock):
    while not stop_event.is_set() and not heartbeat_stop_event.wait(HEARTBEAT_INTERVAL):
        try:
            send_json_locked(sock, {"type": "heartbeat"}, send_lock)
        except OSError as exc:
            print(f"\n[client] heartbeat error: {exc}")
            stop_event.set()
            break


def login_or_register(sock):
    """处理用户注册和登录流程"""
    global current_username
    
    while True:
        print("\n" + "="*40)
        print("1. 登录")
        print("2. 注册")
        print("3. 退出")
        print("="*40)
        
        choice = input("请选择 (1/2/3): ").strip()
        
        if choice == "3":
            return None, False
        
        username = input("用户名: ").strip()
        if not username:
            print("[client] 用户名不能为空")
            continue
        
        password = getpass.getpass("密码: ").strip()
        if not password:
            print("[client] 密码不能为空")
            continue
        
        if choice == "2":
            if len(password) < 6:
                print("[client] 密码长度不能少于6位")
                continue
            
            send_json(sock, {"type": "register", "username": username, "password": password})
            response = recv_json(sock)
            
            if response and response.get("type") == "register_success":
                print(f"[client] {response.get('content', '注册成功')}")
                print("[client] 请登录")
                continue
            else:
                error_msg = response.get("content", "注册失败") if response else "注册失败"
                print(f"[client] {error_msg}")
                continue
        
        elif choice == "1":
            send_json(sock, {"type": "login", "username": username, "password": password})
            response = recv_json(sock)
            
            if response and response.get("type") == "login_success":
                print(f"[client] {response.get('content', '登录成功')}")
                current_username = username
                return username, True
            else:
                error_msg = response.get("content", "登录失败") if response else "登录失败"
                print(f"[client] {error_msg}")
                continue


def main():
    global current_username, message_map
    
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
    
    username, success = login_or_register(sock)
    if not success:
        sock.close()
        return

    print("[client] 聊天已开始，输入消息按回车发送")
    print("[client] 命令列表:")
    print("  /msg <用户名> <消息>  - 私聊")
    print("  /gmsg <群名> <消息>  - 群聊")
    print("  /create_group <群名> - 创建群组")
    print("  /join_group <群名>   - 加入群组")
    print("  /leave_group <群名>  - 退出群组")
    print("  /recall <消息ID>     - 撤回消息(2分钟内)")
    print("  /history             - 查看历史消息")
    print("  /online              - 查看在线用户")
    print("  /quit                - 退出程序")

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
            elif text == "/online":
                send_json_locked(sock, {"type": "online_list"}, send_lock)
            elif text == "/history":
                send_json_locked(sock, {"type": "history"}, send_lock)
            elif text == "/recall":
                print("用法：/recall <消息ID>")
            elif text.startswith("/recall "):
                parts = text.split(maxsplit=1)
                target_id = parts[1].strip()
                if target_id:
                    send_json_locked(sock, {"type": "recall_request", "msg_id": target_id}, send_lock)
                    print(f"[client] 已发送撤回请求，ID: {target_id}")
            elif text == "/msg":
                print("用法：/msg <用户名> <消息内容>")
            elif text.startswith("/msg "):
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    print("用法：/msg <用户名> <消息内容>")
                else:
                    send_json_locked(sock, {"type": "private_msg", "to": parts[1], "content": parts[2]}, send_lock)
            elif text == "/gmsg":
                print("用法：/gmsg <群名> <消息内容>")
            elif text.startswith("/gmsg "):
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    print("用法：/gmsg <群名> <消息内容>")
                else:
                    send_json_locked(sock, {"type": "group_msg", "group": parts[1], "content": parts[2]}, send_lock)
            elif text == "/create_group":
                print("用法：/create_group <群名>")
            elif text.startswith("/create_group "):
                group_name = text.split(maxsplit=1)[1].strip()
                if group_name:
                    send_json_locked(sock, {"type": "group_create", "group": group_name}, send_lock)
            elif text == "/join_group":
                print("用法：/join_group <群名>")
            elif text.startswith("/join_group "):
                group_name = text.split(maxsplit=1)[1].strip()
                if group_name:
                    send_json_locked(sock, {"type": "group_join", "group": group_name}, send_lock)
            elif text == "/leave_group":
                print("用法：/leave_group <群名>")
            elif text.startswith("/leave_group "):
                group_name = text.split(maxsplit=1)[1].strip()
                if group_name:
                    send_json_locked(sock, {"type": "group_leave", "group": group_name}, send_lock)
            elif not text:
                continue
            else:
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