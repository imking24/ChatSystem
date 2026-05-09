from database.db_manager import DBManager

class HistoryManager:
    def __init__(self):
        self.db = DBManager()

    def get_chat_history(self, user1, user2, count=50):
        """
        获取两个用户之间的私聊历史
        """
        history = self.db.get_history(user1, user2, limit=count)
        
        #如果某条消息被撤回了就替换掉
        formatted_history = []
        for msg in history:
            if msg['is_recalled'] == 1:
                msg['content'] = "该消息已撤回"
            formatted_history.append(msg)
            
        return {"status": "success", "history": formatted_history}

    def recall_specific_message(self, msg_id, sender_id):
        """
        执行撤回操作
        """
        success = self.db.recall_message(msg_id, sender_id)
        if success:
            return {"status": "success", "message": "消息已撤回"}
        else:
            return {"status": "fail", "message": "撤回失败"}

# --- 自测部分 ---
if __name__ == "__main__":
    hm = HistoryManager()
    print("获取历史:", hm.get_chat_history("Alice", "Bob"))