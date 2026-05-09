import time
from database.db_manager import DBManager

class SessionManager:
    def __init__(self):
        self.db = DBManager()
        # 在线字典 { 用户名: 最后活跃时间戳 }
        self.active_sessions = {} 
        # 如果30s内没发消息也没有回复心跳包就认为离线
        self.timeout = 30 

    def update_heartbeat(self, username):
        """
        收到用户任何消息或心跳包时调用
        """
        self.active_sessions[username] = time.time()
        # 确保数据库里他是“在线”状态
        self.db.update_user_status(username, 1)
        print(f"用户 {username} 在线")

    def check_dead_sessions(self):
        """
        清理超时的用户（这个函数通常放在一个死循环里跑）
        """
        now = time.time()
        dead_users = []

        for username, last_time in list(self.active_sessions.items()):
            if now - last_time > self.timeout:
                dead_users.append(username)

        for username in dead_users:
            print(f"用户 {username} 已下线")
            self.db.update_user_status(username, 0)
            del self.active_sessions[username]

# --- 自测部分 ---
if __name__ == "__main__":
    sm = SessionManager()
    
    # 1. 模拟 Alice 上线
    sm.update_heartbeat("Alice")
    
    # 2. 模拟时间流逝（假设等了 2 秒，还没到 30 秒）
    time.sleep(2)
    sm.check_dead_sessions()
    print("目前在线名单:", list(sm.active_sessions.keys()))