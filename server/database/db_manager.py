import sqlite3
import os
from datetime import datetime

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
        self._init_db()

    def _get_connection(self):
        """获取数据库连接，设置 row_factory 方便通过列名访问数据"""
        conn = sqlite3.connect(self.db_path)
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
            
            # 2. 消息表：普通消息与文件元数据。0: 正常, 1: 已撤回
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT NOT NULL,
                    content TEXT,                        
                    msg_type TEXT NOT NULL,              
                    filename TEXT,                       
                    file_size INTEGER,                   
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_recalled INTEGER DEFAULT 0        
                )
            ''')
            conn.commit()
            print(">>> [DBManager] 数据库协议适配完成，表结构就绪。")

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

    def save_chat_message(self, msg_dict):
        """ 'message' 类型"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, receiver_id, content, msg_type, timestamp) 
                VALUES (?, ?, ?, ?, ?)
            ''', (msg_dict['sender'], msg_dict['receiver'], msg_dict['content'], 
                  msg_dict['type'], msg_dict['timestamp']))
            conn.commit()
            return cursor.lastrowid

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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 只筛选普通对话和文件发送记录
            cursor.execute('''
                SELECT * FROM messages 
                WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
                AND msg_type IN ('message', 'file_start')
                ORDER BY timestamp DESC LIMIT ?
            ''', (user1, user2, user2, user1, limit))
            return [
                {**dict(row), 'content': '此消息已撤回' if row['is_recalled'] else row['content']} 
                for row in cursor.fetchall()
            ]                   

    def recall_message(self, msg_id, sender_id):
        """撤回功能：仅限发送者本人"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_recalled = 1 WHERE msg_id = ? AND sender_id = ?", 
                           (msg_id, sender_id))
            conn.commit()
            return cursor.rowcount > 0

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