from database.db_manager import DBManager

class UserHandler:
    def __init__(self):
        # 初始化数据库管理器
        self.db = DBManager()

    def handle_register(self, data):
        """
        处理注册逻辑，data 为解析后的字典
        """
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return {"status": "fail", "message": "用户名或密码不能为空"}
        
        # 校验逻辑：密码长度大于等于6
        if len(password) < 6:
            return {"status": "fail", "message": "注册失败：密码长度不能少于 6 位"}

        # 调用 DBManager 的注册接口
        success, msg = self.db.register_user(username, password)
        if success:
            return {"status": "success", "message": "注册成功"}
        else:
            return {"status": "fail", "message": msg}

    def handle_login(self, data):
        """
        处理登录逻辑
        """
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        # 调用数据库验证
        if self.db.verify_login(username, password):
            #登录即视为第一次心跳
            self.db.update_heartbeat(username) 
            return {
                "status": "success", 
                "message": "登录成功", 
                "username": username
            }
        else:
            return {"status": "fail", "message": "用户名或密码错误"}

# --- 自测部分 ---
if __name__ == "__main__":
    handler = UserHandler()
    
    # 1. 测试注册（使用符合长度的密码）
    print(">>> [测试] 注册新用户:", handler.handle_register({'username': 'Alice', 'password': 'secret123'}))
    
    # 2. 测试登录
    print(">>> [测试] 用户登录:", handler.handle_login({'username': 'Alice', 'password': 'secret123'}))