"""
client_gui.py
Person2(King) 客户端 UI。

特点：
- 使用 tkinter，Windows/Linux/macOS 默认可用，避免 PySide6 依赖错误。
- UI 线程与网络线程通过 queue 解耦，避免界面卡死。
- 支持：注册/登录、私聊/群聊入口、在线列表、历史记录、文件发送、撤回上一条消息。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from client_network import ChatClientNetwork
from client_protocol import (
    MESSAGE_TYPE_RESPONSE,
    MESSAGE_TYPE_MESSAGE,
    MESSAGE_TYPE_HISTORY_RESPONSE,
    MESSAGE_TYPE_ONLINE_LIST,
    MESSAGE_TYPE_RECALL_NOTICE,
    MESSAGE_TYPE_FILE_RECEIVED,
)


class ChatClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("分布式即时聊天系统 - Person2(King) 客户端")
        self.root.geometry("980x680")
        self.root.minsize(900, 600)

        self.event_queue: queue.Queue[dict] = queue.Queue()
        self.net = ChatClientNetwork(on_event=self.event_queue.put)

        self.username: str | None = None
        self.last_msg_id: int | str | None = None

        self._build_ui()
        self._poll_events()

    # --------------------
    # UI 构建
    # --------------------
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_connect_frame()
        self._build_main_frame()
        self._build_status_bar()

    def _build_connect_frame(self):
        frame = ttk.LabelFrame(self.root, text="连接与登录")
        frame.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        for i in range(12):
            frame.columnconfigure(i, weight=0)
        frame.columnconfigure(11, weight=1)

        ttk.Label(frame, text="服务器IP").grid(row=0, column=0, padx=4, pady=6)
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(frame, textvariable=self.host_var, width=14).grid(row=0, column=1, padx=4)

        ttk.Label(frame, text="端口").grid(row=0, column=2, padx=4)
        self.port_var = tk.StringVar(value="9009")
        ttk.Entry(frame, textvariable=self.port_var, width=7).grid(row=0, column=3, padx=4)

        ttk.Button(frame, text="连接", command=self.on_connect).grid(row=0, column=4, padx=4)

        ttk.Separator(frame, orient="vertical").grid(row=0, column=5, sticky="ns", padx=8)

        ttk.Label(frame, text="用户名").grid(row=0, column=6, padx=4)
        self.username_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.username_var, width=14).grid(row=0, column=7, padx=4)

        ttk.Label(frame, text="密码").grid(row=0, column=8, padx=4)
        self.password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.password_var, width=14, show="*").grid(row=0, column=9, padx=4)

        ttk.Button(frame, text="注册", command=self.on_register).grid(row=0, column=10, padx=4)
        ttk.Button(frame, text="登录", command=self.on_login).grid(row=0, column=11, padx=4, sticky="w")

    def _build_main_frame(self):
        main = ttk.Frame(self.root)
        main.grid(row=1, column=0, padx=10, pady=6, sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # 左侧在线用户/群组
        left = ttk.LabelFrame(main, text="在线用户 / 群组")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.rowconfigure(1, weight=1)

        ttk.Button(left, text="刷新在线列表", command=self.on_refresh_online).grid(row=0, column=0, padx=8, pady=6, sticky="ew")

        self.online_listbox = tk.Listbox(left, width=24, height=22)
        self.online_listbox.grid(row=1, column=0, padx=8, pady=6, sticky="ns")
        self.online_listbox.bind("<<ListboxSelect>>", self.on_select_online)

        group_frame = ttk.LabelFrame(left, text="群组操作")
        group_frame.grid(row=2, column=0, padx=8, pady=8, sticky="ew")
        self.group_var = tk.StringVar(value="group1")
        ttk.Entry(group_frame, textvariable=self.group_var, width=20).grid(row=0, column=0, columnspan=3, padx=4, pady=4, sticky="ew")
        ttk.Button(group_frame, text="建群", command=self.on_create_group).grid(row=1, column=0, padx=2, pady=4)
        ttk.Button(group_frame, text="入群", command=self.on_join_group).grid(row=1, column=1, padx=2, pady=4)
        ttk.Button(group_frame, text="退群", command=self.on_leave_group).grid(row=1, column=2, padx=2, pady=4)

        # 右侧聊天区
        right = ttk.LabelFrame(main, text="聊天窗口")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        top.columnconfigure(5, weight=1)

        ttk.Label(top, text="目标").grid(row=0, column=0, padx=4)
        self.target_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.target_var, width=20).grid(row=0, column=1, padx=4)

        self.chat_type_var = tk.StringVar(value="private")
        ttk.Radiobutton(top, text="私聊", variable=self.chat_type_var, value="private").grid(row=0, column=2, padx=4)
        ttk.Radiobutton(top, text="群聊", variable=self.chat_type_var, value="group").grid(row=0, column=3, padx=4)

        ttk.Button(top, text="拉取历史", command=self.on_history).grid(row=0, column=4, padx=4)
        ttk.Button(top, text="撤回上一条", command=self.on_recall).grid(row=0, column=5, padx=4, sticky="w")

        self.chat_text = scrolledtext.ScrolledText(right, wrap=tk.WORD, state="disabled")
        self.chat_text.grid(row=1, column=0, padx=8, pady=4, sticky="nsew")

        bottom = ttk.Frame(right)
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        bottom.columnconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(bottom, textvariable=self.input_var)
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.input_entry.bind("<Return>", lambda e: self.on_send())

        ttk.Button(bottom, text="发送", command=self.on_send).grid(row=0, column=1, padx=3)
        ttk.Button(bottom, text="发送文件", command=self.on_send_file).grid(row=0, column=2, padx=3)
        ttk.Button(bottom, text="@AI", command=self.on_ai_shortcut).grid(row=0, column=3, padx=3)

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="未连接")
        bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        bar.grid(row=2, column=0, sticky="ew")

    # --------------------
    # 事件处理：按钮
    # --------------------
    def on_connect(self):
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            self.net.connect(host, port)
            self.status_var.set(f"已连接 {host}:{port}")
        except Exception as e:
            messagebox.showerror("连接失败", str(e))

    def on_register(self):
        try:
            self._ensure_connected()
            username, password = self._get_user_pass()
            self.net.register(username, password)
        except Exception as e:
            messagebox.showerror("注册失败", str(e))

    def on_login(self):
        try:
            self._ensure_connected()
            username, password = self._get_user_pass()
            self.username = username
            self.net.login(username, password)
            self.status_var.set(f"登录请求已发送：{username}")
        except Exception as e:
            messagebox.showerror("登录失败", str(e))

    def on_refresh_online(self):
        try:
            self.net.request_online_list()
        except Exception as e:
            messagebox.showwarning("提示", str(e))

    def on_select_online(self, event):
        selection = self.online_listbox.curselection()
        if not selection:
            return
        value = self.online_listbox.get(selection[0])
        # 格式可能是 "Alice 在线"，取第一个空格前
        target = value.split()[0]
        self.target_var.set(target)
        self.chat_type_var.set("private")

    def on_create_group(self):
        try:
            self.net.create_group(self.group_var.get().strip())
        except Exception as e:
            messagebox.showwarning("建群失败", str(e))

    def on_join_group(self):
        try:
            group = self.group_var.get().strip()
            self.net.join_group(group)
            self.target_var.set(group)
            self.chat_type_var.set("group")
        except Exception as e:
            messagebox.showwarning("入群失败", str(e))

    def on_leave_group(self):
        try:
            self.net.leave_group(self.group_var.get().strip())
        except Exception as e:
            messagebox.showwarning("退群失败", str(e))

    def on_history(self):
        try:
            target = self._get_target()
            self.net.request_history(target)
        except Exception as e:
            messagebox.showwarning("历史记录失败", str(e))

    def on_recall(self):
        try:
            if not self.last_msg_id:
                messagebox.showinfo("提示", "没有可撤回的消息 ID。请等待服务端返回 msg_id，或先发送一条消息。")
                return
            self.net.recall_message(self.last_msg_id)
        except Exception as e:
            messagebox.showwarning("撤回失败", str(e))

    def on_send(self):
        try:
            content = self.input_var.get().strip()
            if not content:
                return
            target = self._get_target()
            chat_type = self.chat_type_var.get()

            client_msg_id = self.net.send_text(target, content, chat_type)
            self._append_chat(f"[我 -> {target}] {content}\n")
            self._append_chat(f"    本地消息ID: {client_msg_id}，等待服务端返回数据库 msg_id\n", tag="hint")
            self.input_var.set("")
        except Exception as e:
            messagebox.showwarning("发送失败", str(e))

    def on_ai_shortcut(self):
        current = self.input_var.get()
        if not current.startswith("@AI"):
            self.input_var.set("@AI " + current)
        self.input_entry.focus_set()

    def on_send_file(self):
        try:
            target = self._get_target()
            path = filedialog.askopenfilename(title="选择要发送的文件")
            if not path:
                return

            chat_type = self.chat_type_var.get()
            self._append_chat(f"[系统] 开始发送文件：{path}\n")

            # 文件发送可能较慢，放到后台，避免 UI 卡死
            threading.Thread(
                target=self._send_file_worker,
                args=(target, path, chat_type),
                daemon=True,
            ).start()
        except Exception as e:
            messagebox.showwarning("发送文件失败", str(e))

    def _send_file_worker(self, target: str, path: str, chat_type: str):
        try:
            self.net.send_file(target, path, chat_type)
            self.event_queue.put({"type": "client_log", "message": "文件发送完成"})
        except Exception as e:
            self.event_queue.put({"type": "client_error", "message": f"文件发送失败：{e}"})

    # --------------------
    # 事件处理：网络回调
    # --------------------
    def _poll_events(self):
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_net_event(event)

        self.root.after(100, self._poll_events)

    def _handle_net_event(self, event: dict):
        msg_type = event.get("type", "")

        if msg_type in {"client_log", "client_error"}:
            self._append_chat(f"[系统] {event.get('message')}\n")
            self.status_var.set(event.get("message", ""))
            return

        if msg_type == MESSAGE_TYPE_RESPONSE:
            status = event.get("status", "")
            message = event.get("message", "")
            self._append_chat(f"[服务端响应] {status}: {message}\n")

            # 服务端可在 response 中带 msg_id，便于撤回
            if event.get("msg_id") is not None:
                self.last_msg_id = event.get("msg_id")
                self._append_chat(f"[系统] 已记录可撤回 msg_id = {self.last_msg_id}\n")

            # 登录成功后刷新在线列表
            if "登录成功" in message or status == "success":
                try:
                    self.net.request_online_list()
                except Exception:
                    pass
            return

        if msg_type == MESSAGE_TYPE_MESSAGE:
            sender = event.get("sender", "")
            receiver = event.get("receiver", "")
            content = event.get("content", "")
            msg_id = event.get("msg_id")
            if msg_id is not None and sender == self.username:
                self.last_msg_id = msg_id
            self._append_chat(f"[{sender} -> {receiver}] {content}\n")
            if msg_id is not None:
                self._append_chat(f"    msg_id={msg_id}\n", tag="hint")
            return

        if msg_type == MESSAGE_TYPE_HISTORY_RESPONSE:
            history = event.get("history", [])
            self._append_chat("\n========== 历史记录 ==========\n")
            if not history:
                self._append_chat("[历史] 暂无记录\n")
            for item in reversed(history):
                ts = item.get("timestamp", "")
                sender = item.get("sender_id") or item.get("sender", "")
                content = item.get("content", "")
                msg_id = item.get("msg_id", "")
                recalled = item.get("is_recalled", 0)
                tag = "已撤回" if recalled else "正常"
                self._append_chat(f"[{ts}] ({tag}, id={msg_id}) {sender}: {content}\n")
            self._append_chat("========== 历史结束 ==========\n\n")
            return

        if msg_type == MESSAGE_TYPE_ONLINE_LIST:
            users = event.get("users", [])
            self.online_listbox.delete(0, tk.END)
            for u in users:
                if isinstance(u, dict):
                    name = u.get("username", "")
                    status = "在线" if u.get("status", 1) else "离线"
                    self.online_listbox.insert(tk.END, f"{name} {status}")
                else:
                    self.online_listbox.insert(tk.END, str(u))
            self._append_chat("[系统] 在线列表已刷新\n")
            return

        if msg_type == MESSAGE_TYPE_RECALL_NOTICE:
            msg_id = event.get("msg_id", "")
            sender = event.get("sender", "")
            self._append_chat(f"[撤回通知] {sender} 撤回了消息 id={msg_id}\n")
            return

        if msg_type == MESSAGE_TYPE_FILE_RECEIVED:
            sender = event.get("sender", "")
            filename = event.get("filename", "")
            saved_path = event.get("saved_path", "")
            self._append_chat(f"[文件] 收到 {sender} 发送的文件：{filename}\n保存位置：{saved_path}\n")
            return

        if msg_type == "file_send_progress":
            self.status_var.set(f"发送 {event.get('filename')}：{event.get('sent_chunks')}/{event.get('total_chunks')}")
            return

        if msg_type == "file_recv_progress":
            total = event.get("total_chunks") or "?"
            self.status_var.set(f"接收 {event.get('filename')}：{event.get('received_chunks')}/{total}")
            return

        # 未知消息直接展示，方便和 Person4 调试接口
        self._append_chat(f"[调试] 收到未知消息：{event}\n")

    # --------------------
    # 工具方法
    # --------------------
    def _ensure_connected(self):
        if not self.net.is_connected():
            raise RuntimeError("请先连接服务器")

    def _get_user_pass(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            raise ValueError("用户名或密码不能为空")
        return username, password

    def _get_target(self):
        target = self.target_var.get().strip()
        if not target:
            raise ValueError("请填写目标用户或群组名")
        return target

    def _append_chat(self, text: str, tag: str | None = None):
        self.chat_text.configure(state="normal")
        if tag == "hint":
            self.chat_text.insert(tk.END, text)
        else:
            self.chat_text.insert(tk.END, text)
        self.chat_text.see(tk.END)
        self.chat_text.configure(state="disabled")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        try:
            self.net.disconnect()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    ChatClientGUI().run()
