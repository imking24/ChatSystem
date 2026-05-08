import sqlite3
import os
from datetime import datetime

class DBManager:
    def __init__(self, db_path=None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "chat_system.db")
        else:
            self.db_path = db_path
            
        self._init_db()

    def _get_connection(self):
        """获取数据库连接，设置 row_factory 方便按字段名取值"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row 
        return conn

    def _init_db(self):
        """数据库设计：初始化表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 用户表：uid, 用户名, 密码, 在线状态
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    uid INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    status INTEGER DEFAULT 0
                )
            ''')
            
            # 消息表：msg_id, 发送者, 接收者, 内容, 类型, 时间, 是否撤回
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT NOT NULL,
                    content TEXT,
                    msg_type TEXT DEFAULT 'private', -- 'private' 或 'group'
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_recalled INTEGER DEFAULT 0    -- 0: 正常, 1: 已撤回
                )
            ''')
            conn.commit()
            print("数据库初始化成功，表结构已准备就绪。")

    # --- 用户管理模块 ---

    def register_user(self, username, password):
        """用户注册：用户名唯一性校验已通过数据库 UNIQUE 约束实现"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
                return True, "注册成功"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"
        except Exception as e:
            return False, str(e)

    def verify_login(self, username, password):
        """登录验证"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
            return user is not None

    def update_user_status(self, username, status):
        """更新在线/离线状态 (1在线, 0离线)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = ? WHERE username = ?", (status, username))
            conn.commit()

    # --- 消息与历史记录模块 ---

    def save_message(self, sender, receiver, content, msg_type='private'):
        """存储消息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, receiver_id, content, msg_type) 
                VALUES (?, ?, ?, ?)
            ''', (sender, receiver, content, msg_type))
            conn.commit()
            return cursor.lastrowid # 返回这条消息的 ID，方便撤回功能使用

    def get_history(self, user1, user2, limit=50):
        """查询两个用户之间的私聊历史记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages 
                WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
                AND msg_type = 'private'
                ORDER BY timestamp DESC LIMIT ?
            ''', (user1, user2, user2, user1, limit))
            # 转换为字典列表方便 JSON 传输
            return [dict(row) for row in cursor.fetchall()]

    def recall_message(self, msg_id, sender_id):
        """消息撤回：只有发送者自己能撤回"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_recalled = 1 WHERE msg_id = ? AND sender_id = ?", (msg_id, sender_id))
            conn.commit()
            return cursor.rowcount > 0 # 返回是否成功修改了记录

# 测试代码
if __name__ == "__main__":
    db = DBManager()
    # 模拟注册
    print(db.register_user("Alice", "123456"))
    # 模拟存储消息
    m_id = db.save_message("Alice", "Bob", "你好呀！")
    print(f"存入消息 ID: {m_id}")