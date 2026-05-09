import time
from database.db_manager import DBManager

class SessionManager:
    def __init__(self):
        """
        初始化会话管理器
        """
        self.db = DBManager()
        # 内存中的在线字典 { 用户名: 最后活跃时间戳 }
        self.active_sessions = {} 
        # 30s内没发消息或心跳包则视为掉线
        self.timeout = 30 

    def update_heartbeat(self, username):
        """
        收到用户任何消息或心跳包时调用
        """
        # 1. 更新内存状态，用于快速检测
        self.active_sessions[username] = time.time()
        # 2. 同步到数据库
        self.db.update_heartbeat(username)
        print(f">>> [Session] 用户 {username} 状态更新：在线")

    def check_dead_sessions(self):
        """
        清理超时的用户
        """
        now = time.time()
        dead_users = []

        # 使用 list(...) 避免在迭代时因删除元素导致报错
        for username, last_time in list(self.active_sessions.items()):
            if now - last_time > self.timeout:
                dead_users.append(username)

        for username in dead_users:
            print(f">>> [Session] 用户 {username} 已超时下线")
            # 调用底层数据库逻辑将状态置为 0, 如果 DBManager 已经有 check_dead_users，可以直接利用
            self.db.check_dead_users(self.timeout) 
            # 清理内存
            if username in self.active_sessions:
                del self.active_sessions[username]

# --- 自测部分 ---
if __name__ == "__main__":
    sm = SessionManager()
    
    # 测试 1: 模拟 Alice 登录并发送心跳
    print("--- 测试 1: 用户上线 ---")
    sm.update_heartbeat("Alice")
    
    # 测试 2: 模拟正常心跳间隔
    print("\n--- 测试 2: 正常时间流逝 ---")
    time.sleep(2)
    sm.check_dead_sessions()
    print("当前在线名单:", list(sm.active_sessions.keys()))
    
    # 测试 3: 模拟超时逻辑 (为了自测快速，这里临时改短超时时间)
    print("\n--- 测试 3: 模拟超时掉线 ---")
    sm.timeout = 1 
    time.sleep(2)
    sm.check_dead_sessions()
    print("超时后在线名单:", list(sm.active_sessions.keys()))