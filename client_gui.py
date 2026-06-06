import json
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk


HOST = "127.0.0.1"
PORT = 9000
HEARTBEAT_INTERVAL = 10


class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("分布式即时聊天系统客户端")
        self.root.geometry("1100x720")
        self.root.minsize(960, 620)
        self.root.configure(bg="#f5f7fb")

        self.sock = None
        self.connected = False
        self.logged_in = False
        self.username = ""
        self.recv_buffer = bytearray()
        self.send_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.heartbeat_stop_event = threading.Event()
        self.receive_thread = None
        self.heartbeat_thread = None
        self.last_sent_message_id = None

        self.chat_mode = tk.StringVar(value="private")
        self.status_var = tk.StringVar(value="未连接")
        self.server_ip_var = tk.StringVar(value=HOST)
        self.port_var = tk.StringVar(value=str(PORT))
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.group_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.message_var = tk.StringVar()

        self.configure_style()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#f5f7fb")
        style.configure("TLabelframe", background="#f5f7fb", bordercolor="#d7deea")
        style.configure("TLabelframe.Label", background="#f5f7fb", foreground="#233044", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabel", background="#f5f7fb", foreground="#233044", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(8, 4))
        style.configure("TRadiobutton", background="#f5f7fb", foreground="#233044", font=("Microsoft YaHei UI", 9))
        style.configure("Status.TLabel", background="#e9eef7", foreground="#233044", padding=(10, 6))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 4))

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.LabelFrame(self.root, text="连接与登录")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        for index in range(14):
            top.columnconfigure(index, weight=0)
        top.columnconfigure(13, weight=1)

        ttk.Label(top, text="服务器 IP").grid(row=0, column=0, padx=(10, 4), pady=10, sticky="w")
        ttk.Entry(top, textvariable=self.server_ip_var, width=16).grid(row=0, column=1, padx=(0, 10), pady=10)
        ttk.Label(top, text="端口").grid(row=0, column=2, padx=(0, 4), pady=10, sticky="w")
        ttk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=(0, 10), pady=10)
        ttk.Button(top, text="连接", width=10, command=self.connect_server).grid(row=0, column=4, padx=(0, 18), pady=10)

        ttk.Label(top, text="用户名").grid(row=0, column=5, padx=(0, 4), pady=10, sticky="w")
        ttk.Entry(top, textvariable=self.username_var, width=16).grid(row=0, column=6, padx=(0, 10), pady=10)
        ttk.Label(top, text="密码").grid(row=0, column=7, padx=(0, 4), pady=10, sticky="w")
        ttk.Entry(top, textvariable=self.password_var, show="*", width=16).grid(row=0, column=8, padx=(0, 10), pady=10)
        ttk.Button(top, text="注册", width=10, command=self.register_user).grid(row=0, column=9, padx=(0, 8), pady=10)
        ttk.Button(top, text="登录", width=10, style="Accent.TButton", command=self.login).grid(row=0, column=10, padx=(0, 10), pady=10)

        main = ttk.Frame(self.root)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self.build_left_panel(main)
        self.build_chat_panel(main)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        status_bar.grid(row=2, column=0, sticky="ew")

    def build_left_panel(self, parent):
        left = ttk.LabelFrame(parent, text="在线用户 / 群组")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Button(left, text="刷新在线列表", width=18, command=self.request_online_list).grid(
            row=0, column=0, sticky="ew", padx=10, pady=(10, 8)
        )

        list_frame = ttk.Frame(left)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.user_listbox = tk.Listbox(
            list_frame,
            width=28,
            height=20,
            activestyle="dotbox",
            bg="#ffffff",
            fg="#1f2937",
            selectbackground="#dbeafe",
            selectforeground="#0f172a",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            font=("Microsoft YaHei UI", 10),
        )
        self.user_listbox.grid(row=0, column=0, sticky="nsew")
        self.user_listbox.bind("<Double-Button-1>", self.on_user_double_click)

        user_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.user_listbox.yview)
        user_scrollbar.grid(row=0, column=1, sticky="ns")
        self.user_listbox.configure(yscrollcommand=user_scrollbar.set)

        group_frame = ttk.Frame(left)
        group_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        group_frame.columnconfigure(0, weight=1)

        ttk.Label(group_frame, text="群名").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(group_frame, textvariable=self.group_var).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        buttons = ttk.Frame(group_frame)
        buttons.grid(row=2, column=0, sticky="ew")
        for index in range(3):
            buttons.columnconfigure(index, weight=1)
        ttk.Button(buttons, text="建群", width=8, command=self.create_group).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ttk.Button(buttons, text="入群", width=8, command=self.join_group).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(buttons, text="退群", width=8, command=self.leave_group).grid(row=0, column=2, padx=(4, 0), sticky="ew")

    def build_chat_panel(self, parent):
        right = ttk.LabelFrame(parent, text="聊天窗口")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        controls = ttk.Frame(right)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="目标").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.target_var).grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Radiobutton(controls, text="私聊", variable=self.chat_mode, value="private").grid(row=0, column=2, padx=(0, 6))
        ttk.Radiobutton(controls, text="群聊", variable=self.chat_mode, value="group").grid(row=0, column=3, padx=(0, 12))
        ttk.Button(controls, text="拉取历史", width=10, command=self.request_history).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(controls, text="撤回上一条", width=12, command=self.recall_last).grid(row=0, column=5)

        chat_frame = ttk.Frame(right)
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat_text = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            bg="#ffffff",
            fg="#111827",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=10,
            font=("Microsoft YaHei UI", 10),
            spacing1=2,
            spacing3=4,
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew")

        chat_scrollbar = ttk.Scrollbar(chat_frame, orient="vertical", command=self.chat_text.yview)
        chat_scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_text.configure(yscrollcommand=chat_scrollbar.set)
        self.configure_text_tags()

        input_frame = ttk.Frame(right)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)

        self.message_entry = ttk.Entry(input_frame, textvariable=self.message_var)
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.message_entry.bind("<Return>", lambda _event: self.send_message())
        ttk.Button(input_frame, text="发送", width=10, style="Accent.TButton", command=self.send_message).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(input_frame, text="@AI", width=8, command=self.send_ai_message).grid(row=0, column=2)

    def configure_text_tags(self):
        self.chat_text.tag_configure("system", foreground="#6b7280")
        self.chat_text.tag_configure("error", foreground="#dc2626")
        self.chat_text.tag_configure("private", foreground="#2563eb")
        self.chat_text.tag_configure("group", foreground="#16a34a")
        self.chat_text.tag_configure("ai", foreground="#9333ea")
        self.chat_text.tag_configure("normal", foreground="#111827")

    def set_status(self, text):
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self.root.after(0, self.status_var.set, text)

    def append_message(self, text, tag=None):
        tag = tag or "normal"

        def update():
            self.chat_text.configure(state="normal")
            self.chat_text.insert("end", text + "\n", tag)
            self.chat_text.configure(state="disabled")
            self.chat_text.see("end")

        if threading.current_thread() is threading.main_thread():
            update()
        else:
            self.root.after(0, update)

    def connect_server(self):
        if self.connected:
            self.set_status("已连接")
            return

        host = self.server_ip_var.get().strip()
        port_text = self.port_var.get().strip()
        if not host:
            self.set_status("错误：服务器 IP 不能为空")
            return
        try:
            port = int(port_text)
        except ValueError:
            self.set_status("错误：端口必须是数字")
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
        except OSError as exc:
            self.sock = None
            self.connected = False
            self.set_status(f"错误：连接失败 {exc}")
            self.append_message(f"[错误] 连接失败：{exc}", "error")
            return

        self.connected = True
        self.stop_event.clear()
        self.heartbeat_stop_event.clear()
        self.recv_buffer.clear()
        self.receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.receive_thread.start()
        self.set_status("已连接")
        self.append_message(f"[系统] 已连接到 {host}:{port}", "system")

    def register_user(self):
        self.append_message("[系统] 当前 server.py 未处理 register 消息，请直接使用用户名登录；密码输入框已保留用于后续服务器扩展。", "system")
        self.set_status("注册功能待服务器接入")

    def login(self):
        if not self.ensure_connected():
            return

        username = self.username_var.get().strip()
        if not username:
            self.set_status("错误：用户名不能为空")
            return

        self.username = username
        self.send_json({"type": "login", "username": username})

    def ensure_connected(self):
        if not self.connected or self.sock is None:
            self.set_status("错误：请先连接服务器")
            return False
        return True

    def send_json(self, data):
        if not self.ensure_connected():
            return False

        try:
            line = json.dumps(data, ensure_ascii=False) + "\n"
            payload = line.encode("utf-8")
            with self.send_lock:
                self.sock.sendall(payload)
            return True
        except OSError as exc:
            self.handle_disconnect(f"发送失败：{exc}")
            return False

    def receive_loop(self):
        while not self.stop_event.is_set():
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.handle_disconnect("连接已断开")
                    break
                self.recv_buffer.extend(chunk)
                self.process_recv_buffer()
            except (ConnectionResetError, OSError, ValueError, json.JSONDecodeError) as exc:
                if not self.stop_event.is_set():
                    self.handle_disconnect(f"接收失败：{exc}")
                break

    def process_recv_buffer(self):
        while True:
            newline_index = self.recv_buffer.find(b"\n")
            if newline_index < 0:
                return

            line = self.recv_buffer[:newline_index]
            del self.recv_buffer[: newline_index + 1]
            if not line.strip():
                continue

            message = json.loads(line.decode("utf-8"))
            self.root.after(0, self.handle_server_message, message)

    def handle_server_message(self, message):
        msg_type = message.get("type")

        if msg_type == "system":
            self.append_message(f"[系统] {message.get('content', '')}", "system")
        elif msg_type == "error":
            content = message.get("content", "")
            self.append_message(f"[错误] {content}", "error")
            self.set_status(f"错误：{content}")
        elif msg_type == "login_success":
            self.logged_in = True
            content = message.get("content", "登录成功")
            self.append_message(f"[系统] {content}", "system")
            self.set_status(f"已登录为 {self.username}")
            self.start_heartbeat()
            self.request_online_list()
        elif msg_type == "login_failed":
            content = message.get("content", "")
            self.logged_in = False
            self.append_message(f"[错误] {content}", "error")
            self.set_status(f"错误：{content}")
        elif msg_type in ("online_list", "online"):
            users = message.get("users", [])
            self.update_online_users(users)
            self.set_status("在线列表已刷新")
        elif msg_type in ("private_msg", "msg"):
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            self.append_message(f"[私聊][{sender}] {content}", "private")
        elif msg_type in ("group_msg", "gmsg"):
            group = message.get("group", "unknown")
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            self.append_message(f"[群聊][{group}][{sender}] {content}", "group")
        elif msg_type == "message_sent":
            message_id = message.get("message_id")
            if message_id is not None:
                self.last_sent_message_id = message_id
                self.set_status(f"最近消息 ID：{message_id}，2 分钟内可撤回")
        elif msg_type == "recall_notice":
            message_id = message.get("message_id")
            sender = message.get("from", "unknown")
            if message_id == self.last_sent_message_id:
                self.last_sent_message_id = None
            self.append_message(f"[撤回] {sender} 撤回了一条消息", "system")
        elif msg_type == "chat":
            self.append_message(message.get("content", ""), "normal")
        elif msg_type == "history":
            self.display_history(message.get("messages", []))
        elif msg_type == "ai_response":
            self.append_message(f"[AI助手] {message.get('content', '')}", "ai")
        else:
            self.append_message(f"[调试] {json.dumps(message, ensure_ascii=False)}", "normal")

    def update_online_users(self, users):
        self.user_listbox.delete(0, "end")
        for user in users:
            self.user_listbox.insert("end", user)

    def display_history(self, messages):
        if not messages:
            self.append_message("[历史] 暂无历史消息", "system")
            return

        self.append_message("[历史] 最近消息：", "system")
        for item in messages:
            timestamp = self.format_timestamp(item.get("timestamp", ""))
            msg_type = item.get("msg_type", "")
            sender = item.get("sender", "")
            content = item.get("content", "")

            if msg_type == "private":
                receiver = item.get("receiver", "")
                self.append_message(f"[历史][私聊][{timestamp}][{sender} -> {receiver}] {content}", "private")
            elif msg_type == "group":
                group = item.get("group_name", "")
                self.append_message(f"[历史][群聊][{timestamp}][{group}][{sender}] {content}", "group")
            else:
                self.append_message(f"[历史][{timestamp}] {content}", "normal")

    def format_timestamp(self, timestamp):
        if not timestamp:
            return ""
        return str(timestamp).replace("T", " ")[:16]

    def start_heartbeat(self):
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        self.heartbeat_stop_event.clear()
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def heartbeat_loop(self):
        while not self.stop_event.is_set() and not self.heartbeat_stop_event.wait(HEARTBEAT_INTERVAL):
            if not self.connected or not self.logged_in:
                continue
            try:
                line = json.dumps({"type": "heartbeat"}, ensure_ascii=False) + "\n"
                with self.send_lock:
                    self.sock.sendall(line.encode("utf-8"))
            except OSError as exc:
                self.handle_disconnect(f"心跳失败：{exc}")
                break

    def request_online_list(self):
        if self.send_json({"type": "online_list"}):
            self.set_status("正在刷新在线列表")

    def create_group(self):
        group = self.get_group_name()
        if group:
            if self.send_json({"type": "group_create", "group": group}):
                self.set_status(f"已发送建群请求：{group}")

    def join_group(self):
        group = self.get_group_name()
        if group:
            if self.send_json({"type": "group_join", "group": group}):
                self.target_var.set(group)
                self.chat_mode.set("group")
                self.set_status(f"已发送入群请求：{group}")

    def leave_group(self):
        group = self.get_group_name()
        if group:
            if self.send_json({"type": "group_leave", "group": group}):
                self.set_status(f"已发送退群请求：{group}")

    def get_group_name(self):
        group = self.group_var.get().strip()
        if not group:
            group = self.target_var.get().strip() if self.chat_mode.get() == "group" else ""
        if not group:
            self.set_status("错误：群名不能为空")
            return ""
        return group

    def request_history(self):
        if self.send_json({"type": "history"}):
            self.set_status("正在拉取历史消息")

    def recall_last(self):
        if self.last_sent_message_id is None:
            self.set_status("暂无可撤回的最近消息")
            return
        if self.send_json({"type": "recall", "message_id": self.last_sent_message_id}):
            self.set_status("已发送撤回请求")

    def send_message(self):
        target = self.target_var.get().strip()
        content = self.message_var.get().strip()
        mode = self.chat_mode.get()

        if not content:
            self.set_status("错误：消息不能为空")
            return

        if mode == "private":
            if not target:
                self.set_status("错误：私聊目标不能为空")
                return
            data = {"type": "private_msg", "to": target, "content": content}
        else:
            if not target:
                self.set_status("错误：群名不能为空")
                return
            data = {"type": "group_msg", "group": target, "content": content}

        if self.send_json(data):
            self.message_var.set("")
            self.set_status("发送成功")
            if mode == "private":
                self.append_message(f"[我 -> {target}] {content}", "private")

    def send_ai_message(self):
        if self.chat_mode.get() != "group":
            self.set_status("错误：@AI 请在群聊中使用")
            self.append_message("[错误] @AI 请在群聊中使用", "error")
            return

        group = self.target_var.get().strip()
        content = self.message_var.get().strip()
        if not group:
            self.set_status("错误：群名不能为空")
            return
        if not content:
            self.set_status("错误：请输入问题")
            return

        if self.send_json({"type": "group_msg", "group": group, "content": "@AI " + content}):
            self.message_var.set("")
            self.set_status("@AI 消息已发送")

    def on_user_double_click(self, _event):
        selection = self.user_listbox.curselection()
        if not selection:
            return
        username = self.user_listbox.get(selection[0])
        self.target_var.set(username)
        self.chat_mode.set("private")
        self.set_status(f"已选择私聊目标：{username}")

    def handle_disconnect(self, reason):
        self.connected = False
        self.logged_in = False
        self.stop_event.set()
        self.heartbeat_stop_event.set()
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.root.after(0, self.append_message, f"[系统] {reason}", "system")
        self.set_status("连接已断开")

    def on_close(self):
        self.stop_event.set()
        self.heartbeat_stop_event.set()
        if self.sock is not None:
            try:
                if self.connected:
                    line = json.dumps({"type": "quit"}, ensure_ascii=False) + "\n"
                    with self.send_lock:
                        self.sock.sendall(line.encode("utf-8"))
            except OSError:
                pass
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    ChatClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
