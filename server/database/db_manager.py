import sqlite3
import os
from datetime import datetime
import threading

class DBManager:
    def __init__(self, db_path=None):
        """
        初始化数据库管理器
        :param db_path: 数据库文件路径。如果为None，则在当前脚本目录下创建。
        """
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "chat_system.db")
        else:
            self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self):
        """获取数据库连接，设置 row_factory 方便通过列名访问数据"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row 
        return conn

    def _init_db(self):
        """数据库初始化：根据组长给出的协议规范建立表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 用户表：存储用户信息及心跳状态。0: 离线, 1: 在线
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    uid INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    status INTEGER DEFAULT 0,            
                    last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP 
                )
            ''')
            
            self._ensure_messages_table(cursor)
            conn.commit()
            print(">>> [DBManager] 数据库协议适配完成，表结构就绪。")

    def _ensure_messages_table(self, cursor):
        """创建或迁移消息表到当前聊天系统需要的结构。"""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if cursor.fetchone() is None:
            self._create_messages_table(cursor)
            return

        cursor.execute("PRAGMA table_info(messages)")
        columns = {row["name"] for row in cursor.fetchall()}
        required = {"id", "sender", "receiver", "group_name", "content", "msg_type", "timestamp"}
        if required.issubset(columns):
            return

        cursor.execute("ALTER TABLE messages RENAME TO messages_old")
        self._create_messages_table(cursor)

        old_columns = columns
        sender_expr = "sender_id" if "sender_id" in old_columns else "''"
        receiver_expr = "receiver_id" if "receiver_id" in old_columns else "''"
        content_expr = "content" if "content" in old_columns else "''"
        msg_type_expr = "msg_type" if "msg_type" in old_columns else "'chat'"
        timestamp_expr = "timestamp" if "timestamp" in old_columns else "CURRENT_TIMESTAMP"
        cursor.execute(f'''
            INSERT INTO messages (sender, receiver, group_name, content, msg_type, timestamp)
            SELECT {sender_expr}, {receiver_expr}, NULL, {content_expr}, {msg_type_expr}, {timestamp_expr}
            FROM messages_old
        ''')
        cursor.execute("DROP TABLE messages_old")

    def _create_messages_table(self, cursor):
        cursor.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                receiver TEXT,
                group_name TEXT,
                content TEXT NOT NULL,
                msg_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # --- 用户管理模块  ---

    def register_user(self, username, password):
        """用户注册，防止重名"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
                return True, "注册成功"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"

    def verify_login(self, username, password):
        """登录验证"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            return cursor.fetchone() is not None

    def update_heartbeat(self, username):
        """
        心跳更新：当收到 MESSAGE_TYPE_HEARTBEAT 协议包时调用
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET last_heartbeat = CURRENT_TIMESTAMP, status = 1 
                WHERE username = ?
            ''', (username,))
            conn.commit()

    def check_dead_users(self, timeout_seconds=30):
        """
        自动掉线检测：
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET status = 0 
                WHERE (strftime('%s', 'now') - strftime('%s', last_heartbeat)) > ?
            ''', (timeout_seconds,))
            conn.commit()

    # --- 消息存储与查询 ---

    def save_private_message(self, sender, receiver, content):
        """保存一条私聊消息。"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO messages (sender, receiver, group_name, content, msg_type)
                    VALUES (?, ?, NULL, ?, 'private')
                ''', (sender, receiver, content))
                conn.commit()
                return cursor.lastrowid

    def save_group_message(self, sender, group_name, content):
        """保存一条群聊消息。"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO messages (sender, receiver, group_name, content, msg_type)
                    VALUES (?, NULL, ?, ?, 'group')
                ''', (sender, group_name, content))
                conn.commit()
                return cursor.lastrowid

    def get_recent_history(self, username, group_names=None, limit=20):
        """查询用户最近的相关私聊和群聊消息。"""
        group_names = list(group_names or [])

        private_clause = "(msg_type = 'private' AND (sender = ? OR receiver = ?))"
        params = [username, username]

        if group_names:
            placeholders = ", ".join("?" for _ in group_names)
            where_clause = f"{private_clause} OR (msg_type = 'group' AND group_name IN ({placeholders}))"
            params.extend(group_names)
        else:
            where_clause = private_clause

        params.append(limit)
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT id, sender, receiver, group_name, content, msg_type, timestamp
                    FROM messages
                    WHERE {where_clause}
                    ORDER BY id DESC
                    LIMIT ?
                ''', params)
                rows = [dict(row) for row in cursor.fetchall()]

        return list(reversed(rows))

    def save_chat_message(self, msg_dict):
        """ 'message' 类型"""
        return self.save_private_message(
            msg_dict['sender'],
            msg_dict['receiver'],
            msg_dict['content'],
        )

    def save_file_info(self, msg_dict):
        """ 'file_start' 类型：记录文件传输任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, receiver_id, filename, file_size, msg_type, timestamp) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (msg_dict['sender'], msg_dict['receiver'], msg_dict['filename'], 
                  msg_dict['file_size'], msg_dict['type'], msg_dict['timestamp']))
            conn.commit()
            return cursor.lastrowid

    def get_history(self, user1, user2, limit=50):
        """
        查询历史记录：过滤掉心跳包和文件块，只展示具有展示意义的内容
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM messages 
                    WHERE msg_type = 'private'
                    AND ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
                    ORDER BY id DESC LIMIT ?
                ''', (user1, user2, user2, user1, limit))
                return [dict(row) for row in cursor.fetchall()]

    def recall_message(self, msg_id, sender_id):
        """撤回功能"""
        return False

# --- 模块测试逻辑 ---
if __name__ == "__main__":
    db = DBManager()
    
    # 测试 1: 注册与心跳逻辑
    db.register_user("Alice", "secret123")
    db.update_heartbeat("Alice")
    
    # 测试 2: 模拟收到协议格式的消息并存储
    mock_json_msg = {
        "type": "message",
        "sender": "Alice",
        "receiver": "Bob",
        "content": "第一次测试！",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    msg_id = db.save_chat_message(mock_json_msg)
    print(f"成功存入协议消息，ID 为: {msg_id}")
    
    # 测试 3: 查询历史记录
    history = db.get_history("Alice", "Bob")
    for record in history:
        print(f"[{record['timestamp']}] {record['sender_id']}: {record['content']}")
