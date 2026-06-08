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
        self.root.configure(bg="#05070d")
        self.is_fullscreen = False
        self.set_fullscreen(True)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

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
        self.message_tags = {}
        self.pending_private_messages = []

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

    def set_fullscreen(self, enabled):
        self.is_fullscreen = enabled
        try:
            self.root.attributes("-fullscreen", enabled)
        except tk.TclError:
            if enabled:
                try:
                    self.root.state("zoomed")
                except tk.TclError:
                    pass

    def toggle_fullscreen(self, _event=None):
        self.set_fullscreen(not self.is_fullscreen)

    def exit_fullscreen(self, _event=None):
        if self.is_fullscreen:
            self.set_fullscreen(False)

    def configure_style(self):
        self.colors = {
            "bg": "#05070d",
            "sidebar": "#0a0f1c",
            "panel": "#0d1322",
            "panel_2": "#101827",
            "field": "#151e2e",
            "field_alt": "#0b1020",
            "border": "#263247",
            "text": "#f8fafc",
            "muted": "#94a3b8",
            "cyan": "#22d3ee",
            "blue": "#60a5fa",
            "green": "#34d399",
            "purple": "#c084fc",
            "pink": "#fb7185",
            "amber": "#fbbf24",
            "red": "#f87171",
        }

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Sidebar.TFrame", background=self.colors["sidebar"])
        style.configure("Chat.TFrame", background=self.colors["panel"])
        style.configure("Control.TFrame", background=self.colors["panel_2"])
        style.configure("TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))
        style.configure("Sidebar.TLabel", background=self.colors["sidebar"], foreground=self.colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=self.colors["sidebar"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=self.colors["sidebar"], foreground=self.colors["cyan"], font=("Microsoft YaHei UI", 9))
        style.configure("ChatTitle.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Status.TLabel", background="#08111f", foreground=self.colors["green"], padding=(14, 8), font=("Microsoft YaHei UI", 9))

        for name, background in (("Section", self.colors["sidebar"]), ("Chat", self.colors["panel"])):
            style.configure(
                f"{name}.TLabelframe",
                background=background,
                bordercolor=self.colors["border"],
                borderwidth=1,
                relief="solid",
            )
            style.configure(
                f"{name}.TLabelframe.Label",
                background=background,
                foreground=self.colors["cyan"] if name == "Section" else self.colors["purple"],
                font=("Microsoft YaHei UI", 10, "bold"),
            )

        style.configure(
            "Dark.TEntry",
            fieldbackground=self.colors["field"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            insertcolor=self.colors["text"],
            padding=(8, 6),
        )
        style.map(
            "Dark.TEntry",
            fieldbackground=[("disabled", "#111827"), ("readonly", self.colors["field"]), ("focus", "#182235")],
            foreground=[("disabled", self.colors["muted"])],
            bordercolor=[("focus", self.colors["cyan"])],
        )

        style.configure("TRadiobutton", background=self.colors["panel_2"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))
        style.map(
            "TRadiobutton",
            background=[("active", self.colors["panel_2"])],
            foreground=[("active", self.colors["cyan"]), ("selected", self.colors["cyan"])],
            indicatorcolor=[("selected", self.colors["cyan"]), ("!selected", self.colors["field"])],
        )

        style.configure(
            "TButton",
            background="#172033",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            focusthickness=0,
            font=("Microsoft YaHei UI", 9),
            padding=(10, 6),
        )
        style.map("TButton", background=[("active", "#22304a"), ("pressed", "#0f172a")], foreground=[("disabled", self.colors["muted"])])
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.map("Accent.TButton", background=[("active", "#3b82f6"), ("pressed", "#1d4ed8")])
        style.configure("Success.TButton", background="#059669", foreground="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.map("Success.TButton", background=[("active", "#10b981"), ("pressed", "#047857")])
        style.configure("Warn.TButton", background="#d97706", foreground="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.map("Warn.TButton", background=[("active", "#f59e0b"), ("pressed", "#b45309")])
        style.configure("Danger.TButton", background="#be123c", foreground="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.map("Danger.TButton", background=[("active", "#e11d48"), ("pressed", "#9f1239")])
        style.configure("Ai.TButton", background="#7e22ce", foreground="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.map("Ai.TButton", background=[("active", "#a855f7"), ("pressed", "#6b21a8")])

    def rounded_rect(self, canvas, x1, y1, x2, y2, radius, **options):
        radius = max(1, min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2)))
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=18, **options)

    def glass_button(self, parent, text, command, variant="default", surface="sidebar", width=118):
        palettes = {
            "default": {"bg": "#172033", "hover": "#20304a", "pressed": "#101827", "border": "#4b5873", "glow": "#7c8ca8"},
            "accent": {"bg": "#173261", "hover": "#1f4f9b", "pressed": "#102a52", "border": "#60a5fa", "glow": "#93c5fd"},
            "success": {"bg": "#0f3f36", "hover": "#11634f", "pressed": "#0a2f29", "border": "#34d399", "glow": "#6ee7b7"},
            "warn": {"bg": "#4b3414", "hover": "#7a4d13", "pressed": "#39270f", "border": "#fbbf24", "glow": "#fde68a"},
            "danger": {"bg": "#501827", "hover": "#861638", "pressed": "#3f1320", "border": "#fb7185", "glow": "#fda4af"},
            "ai": {"bg": "#351c5d", "hover": "#5b21b6", "pressed": "#2e1654", "border": "#c084fc", "glow": "#ddd6fe"},
        }
        surfaces = {
            "sidebar": self.colors["sidebar"],
            "panel": self.colors["panel"],
            "panel_2": self.colors["panel_2"],
        }
        palette = palettes.get(variant, palettes["default"])
        surface_color = surfaces.get(surface, self.colors["sidebar"])
        state = {"hover": False, "pressed": False}

        canvas = tk.Canvas(
            parent,
            width=width,
            height=40,
            bg=surface_color,
            cursor="hand2",
            bd=0,
            highlightthickness=0,
            relief="flat",
        )

        def draw():
            width = max(canvas.winfo_width(), 80)
            height = max(canvas.winfo_height(), 40)
            canvas.delete("all")
            inset = 4
            lift = 1
            fill = palette["bg"]
            border = palette["border"]
            shadow = "#080d18"
            text_color = self.colors["text"]

            if state["pressed"]:
                fill = palette["pressed"]
                inset = 5
                lift = 0
                shadow = "#060a13"
            elif state["hover"]:
                fill = palette["hover"]
                border = palette["glow"]
                inset = 3
                lift = 2
                shadow = "#0b1322"

            self.rounded_rect(canvas, 5, 7, width - 3, height - 2, 13, fill=shadow, outline="")
            self.rounded_rect(canvas, inset, inset - lift, width - inset - 2, height - inset - lift, 12, fill=border, outline="")
            self.rounded_rect(canvas, inset + 1, inset + 1 - lift, width - inset - 3, height - inset - 1 - lift, 11, fill=fill, outline="")
            canvas.create_line(
                inset + 10,
                inset + 4 - lift,
                width - inset - 12,
                inset + 4 - lift,
                fill="#ffffff",
                width=1,
                stipple="gray50",
            )
            canvas.create_text(
                width / 2,
                height / 2 - lift,
                text=text,
                fill=text_color,
                font=("Microsoft YaHei UI", 10),
            )

        def enter(_event=None):
            state["hover"] = True
            draw()

        def leave(_event=None):
            state["hover"] = False
            state["pressed"] = False
            draw()

        def press(_event=None):
            state["pressed"] = True
            draw()

        def release(event=None):
            should_run = False
            if event is not None:
                should_run = 0 <= event.x <= canvas.winfo_width() and 0 <= event.y <= canvas.winfo_height()
            state["pressed"] = False
            draw()
            if should_run and command:
                command()

        canvas.bind("<Configure>", lambda _event: draw())
        canvas.bind("<Enter>", enter)
        canvas.bind("<Leave>", leave)
        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<ButtonRelease-1>", release)
        draw()
        return canvas

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, style="TFrame")
        main.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        main.columnconfigure(0, weight=1, uniform="main")
        main.columnconfigure(1, weight=2, uniform="main")
        main.rowconfigure(0, weight=1)

        self.build_left_panel(main)
        self.build_chat_panel(main)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        status_bar.grid(row=1, column=0, sticky="ew")

    def build_left_panel(self, parent):
        left = ttk.Frame(parent, style="Sidebar.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        ttk.Label(left, text="ChatSystem", style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=18, pady=(18, 0))
        ttk.Label(left, text="连接 · 账户 · 群组", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))

        connection = ttk.LabelFrame(left, text="服务器连接", style="Section.TLabelframe")
        connection.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        connection.columnconfigure(0, weight=1)
        connection.columnconfigure(1, weight=0)

        ttk.Label(connection, text="服务器 IP", style="Sidebar.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        ttk.Label(connection, text="端口", style="Sidebar.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 12), pady=(10, 4))
        ttk.Entry(connection, textvariable=self.server_ip_var, style="Dark.TEntry").grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 10))
        ttk.Entry(connection, textvariable=self.port_var, width=8, style="Dark.TEntry").grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 10))
        self.glass_button(connection, text="连接服务器", variant="accent", command=self.connect_server).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12)
        )

        account = ttk.LabelFrame(left, text="账号密码", style="Section.TLabelframe")
        account.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 12))
        account.columnconfigure(0, weight=1)
        account.columnconfigure(1, weight=1)

        ttk.Label(account, text="用户名", style="Sidebar.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))
        ttk.Entry(account, textvariable=self.username_var, style="Dark.TEntry").grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        ttk.Label(account, text="密码", style="Sidebar.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4))
        ttk.Entry(account, textvariable=self.password_var, show="*", style="Dark.TEntry").grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        self.glass_button(account, text="注册", variant="warn", command=self.register_user).grid(row=4, column=0, sticky="ew", padx=(12, 6), pady=(0, 12))
        self.glass_button(account, text="登录", variant="success", command=self.login).grid(row=4, column=1, sticky="ew", padx=(6, 12), pady=(0, 12))

        lower = ttk.Frame(left, style="Sidebar.TFrame")
        lower.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)

        group_frame = ttk.LabelFrame(lower, text="创建群聊", style="Section.TLabelframe")
        group_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        group_frame.columnconfigure(0, weight=1)

        ttk.Label(group_frame, text="群名", style="Sidebar.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        ttk.Entry(group_frame, textvariable=self.group_var, style="Dark.TEntry").grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        buttons = ttk.Frame(group_frame, style="Sidebar.TFrame")
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        for index in range(3):
            buttons.columnconfigure(index, weight=1)
        self.glass_button(buttons, text="建群", variant="accent", command=self.create_group).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.glass_button(buttons, text="入群", variant="success", command=self.join_group).grid(row=0, column=1, padx=5, sticky="ew")
        self.glass_button(buttons, text="退群", variant="danger", command=self.leave_group).grid(row=0, column=2, padx=(5, 0), sticky="ew")

        online = ttk.LabelFrame(lower, text="在线用户", style="Section.TLabelframe")
        online.grid(row=1, column=0, sticky="nsew")
        online.columnconfigure(0, weight=1)
        online.rowconfigure(1, weight=1)

        self.glass_button(online, text="刷新在线列表", command=self.request_online_list).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))

        list_frame = ttk.Frame(online, style="Sidebar.TFrame")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.user_listbox = tk.Listbox(
            list_frame,
            width=24,
            height=20,
            activestyle="dotbox",
            bg=self.colors["field_alt"],
            fg=self.colors["text"],
            selectbackground="#155e75",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["cyan"],
            highlightthickness=1,
            font=("Microsoft YaHei UI", 10),
        )
        self.user_listbox.grid(row=0, column=0, sticky="nsew")
        self.user_listbox.bind("<Double-Button-1>", self.on_user_double_click)

        user_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.user_listbox.yview)
        user_scrollbar.grid(row=0, column=1, sticky="ns")
        self.user_listbox.configure(yscrollcommand=user_scrollbar.set)

    def build_chat_panel(self, parent):
        right = ttk.Frame(parent, style="Chat.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        header = ttk.Frame(right, style="Chat.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="聊天主界面", style="ChatTitle.TLabel").grid(row=0, column=0, sticky="w")

        controls = ttk.Frame(right, style="Control.TFrame")
        controls.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="目标", background=self.colors["panel_2"], foreground=self.colors["muted"]).grid(row=0, column=0, sticky="w", padx=(12, 6), pady=12)
        ttk.Entry(controls, textvariable=self.target_var, style="Dark.TEntry").grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=12)
        ttk.Radiobutton(controls, text="私聊", variable=self.chat_mode, value="private").grid(row=0, column=2, padx=(0, 8), pady=12)
        ttk.Radiobutton(controls, text="群聊", variable=self.chat_mode, value="group").grid(row=0, column=3, padx=(0, 14), pady=12)
        self.glass_button(controls, text="查找历史", variant="warn", surface="panel_2", command=self.request_history).grid(row=0, column=4, padx=(0, 8), pady=12)
        self.glass_button(controls, text="撤回上一条", variant="danger", surface="panel_2", command=self.recall_last).grid(row=0, column=5, padx=(0, 12), pady=12)

        chat_frame = ttk.LabelFrame(right, text="消息", style="Chat.TLabelframe")
        chat_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat_text = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            bg="#070b14",
            fg=self.colors["text"],
            relief="flat",
            borderwidth=0,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["purple"],
            highlightthickness=1,
            insertbackground=self.colors["text"],
            padx=14,
            pady=12,
            font=("Microsoft YaHei UI", 10),
            spacing1=2,
            spacing3=6,
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        chat_scrollbar = ttk.Scrollbar(chat_frame, orient="vertical", command=self.chat_text.yview)
        chat_scrollbar.grid(row=0, column=1, sticky="ns", pady=12)
        self.chat_text.configure(yscrollcommand=chat_scrollbar.set)
        self.configure_text_tags()

        input_frame = ttk.Frame(right, style="Control.TFrame")
        input_frame.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        input_frame.columnconfigure(0, weight=1)

        self.message_entry = ttk.Entry(input_frame, textvariable=self.message_var, style="Dark.TEntry")
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=12)
        self.message_entry.bind("<Return>", lambda _event: self.send_message())
        self.glass_button(input_frame, text="发送", variant="accent", surface="panel_2", width=72, command=self.send_message).grid(row=0, column=1, padx=(0, 6), pady=12)
        self.glass_button(input_frame, text="@AI", variant="ai", surface="panel_2", width=62, command=self.send_ai_message).grid(row=0, column=2, padx=(0, 12), pady=12)

    def configure_text_tags(self):
        self.chat_text.tag_configure("system", foreground=self.colors["muted"])
        self.chat_text.tag_configure("error", foreground=self.colors["red"])
        self.chat_text.tag_configure("private", foreground=self.colors["blue"])
        self.chat_text.tag_configure("group", foreground=self.colors["green"])
        self.chat_text.tag_configure("ai", foreground=self.colors["purple"])
        self.chat_text.tag_configure("normal", foreground=self.colors["text"])

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

    def append_tracked_message(self, text, tag=None, message_id=None, record_tag=None):
        tag = tag or "normal"
        if record_tag is None:
            record_tag = f"msg_{int(time.time() * 1000)}_{len(self.message_tags)}"
        tags = (tag, record_tag)

        def update():
            self.chat_text.configure(state="normal")
            self.chat_text.insert("end", text + "\n", tags)
            self.chat_text.configure(state="disabled")
            self.chat_text.see("end")

        if threading.current_thread() is threading.main_thread():
            update()
        else:
            self.root.after(0, update)

        if message_id is not None:
            self.message_tags[str(message_id)] = record_tag
        return record_tag

    def replace_tracked_message(self, message_id, text, tag=None):
        record_tag = self.message_tags.pop(str(message_id), None)
        if not record_tag:
            return False

        tag = tag or "system"

        def update():
            ranges = self.chat_text.tag_ranges(record_tag)
            if not ranges:
                return
            start = ranges[0]
            end = ranges[-1]
            self.chat_text.configure(state="normal")
            self.chat_text.delete(start, end)
            self.chat_text.insert(start, text + "\n", tag)
            self.chat_text.configure(state="disabled")
            self.chat_text.see("end")

        if threading.current_thread() is threading.main_thread():
            update()
        else:
            self.root.after(0, update)
        return True

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
            if self.pending_private_messages:
                self.pending_private_messages.pop(0)
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
            message_id = message.get("message_id")
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            self.append_tracked_message(f"[私聊][{sender}] {content}", "private", message_id=message_id)
        elif msg_type in ("group_msg", "gmsg"):
            message_id = message.get("message_id")
            group = message.get("group", "unknown")
            sender = message.get("from", "unknown")
            content = message.get("content", "")
            self.append_tracked_message(f"[群聊][{group}][{sender}] {content}", "group", message_id=message_id)
        elif msg_type == "message_sent":
            message_id = message.get("message_id")
            if message_id is not None:
                self.last_sent_message_id = message_id
                if message.get("msg_type") == "private" and self.pending_private_messages:
                    pending = self.pending_private_messages.pop(0)
                    self.append_tracked_message(
                        f"[我 -> {pending['target']}] {pending['content']}",
                        "private",
                        message_id=message_id,
                    )
                self.set_status(f"最近消息 ID：{message_id}，2 分钟内可撤回")
        elif msg_type == "recall_notice":
            message_id = message.get("message_id")
            sender = message.get("from", "unknown")
            if message_id == self.last_sent_message_id:
                self.last_sent_message_id = None
            replaced = self.replace_tracked_message(message_id, f"[撤回] {sender} 撤回了一条消息", "system")
            if not replaced:
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
                self.pending_private_messages.append({"target": target, "content": content})

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
