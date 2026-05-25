from database.db_manager import DBManager

class HistoryManager:
    def __init__(self):
        """
        初始化历史记录管理器，连接底层数据库管理器 DBManager
        """
        self.db = DBManager()

    def get_chat_history(self, user1, user2, count=50):
        """
        获取两个用户之间的私聊历史，返回包含 status 和 history 的字典
        """
        try:
            # 1. 调用底层接口   
            history = self.db.get_history(user1, user2, limit=count)
            # 2. 这里的 history 已经是处理好的列表（包含 timestamp, sender_id, content 等）
            return {
                "status": "success", 
                "history": history
            }
        except Exception as e:
            # 异常处理
            return {
                "status": "fail", 
                "message": f"查询历史记录时发生错误: {str(e)}"
            }

    def recall_specific_message(self, msg_id, sender_id):
        """
        执行撤回操作：调用底层的权限校验撤回逻辑
        """
        try:
            # 调用底层 recall_message，检查 msg_id 和 sender_id 是否匹配
            success, reason, _message = self.db.recall_message(msg_id, sender_id)
            
            if success:
                return {"status": "success", "message": "消息已撤回"}
            else:
                # 如果 rowcount 为 0，说明消息不存在或 sender_id 不对
                return {"status": "fail", "message": "撤回失败：消息不存在或您没有撤回权限"}
        except Exception as e:
            return {"status": "fail", "message": f"执行撤回时发生错误: {str(e)}"}

# --- 自测部分 ---
if __name__ == "__main__":
    hm = HistoryManager()
        
    # 模拟查询 Alice 和 Bob 的记录
    # 假设 DBManager 中已经有之前存入的测试数据
    test_res = hm.get_chat_history("Alice", "Bob")
    
    if test_res["status"] == "success":
        print(f"成功获取到 {len(test_res['history'])} 条历史记录：")
        for msg in test_res["history"]:
            status_tag = "[已撤回]" if msg.get('is_recalled') else "[正常]"
            print(f"{status_tag} {msg['sender_id']}: {msg['content']}")
    else:
        print(f"查询失败: {test_res['message']}")
