import socket
import struct
import json
from typing import Any, Dict, Optional


class Message:
    # this is a message encode/decode tool

    @staticmethod
    def send_json(sock:socket.socket,obj:Dict[str,Any]) -> None:
        """
        json格式：【4字节长度】【json内容】
        """
        data = json.dumps(obj,ensure_ascii=False).encode('utf-8')
        # 前四个字节存储消息长度
        msg = struct.pack('>I', len(data)) + data
        sock.sendall(msg)
    
    @staticmethod
    def recv_json(sock:socket.socket) -> Optional[Dict[str,Any]]:
        """
        返回NONE表示已关闭连接
        """
        # 先读取 4 字节长度
        raw_msglen = Message._recvall(sock, 4)
        if not raw_msglen:
            return None
        
        msglen = struct.unpack('>I', raw_msglen)[0]
        
        # 再读取消息内容
        data = Message._recvall(sock, msglen)
        if not data:
            return None
        
        return json.loads(data.decode('utf-8'))
    
    @staticmethod
    def _recvall(sock: socket.socket, n: int) -> Optional[bytes]:
        """
        确保接收 n 字节
        处理 TCP 分片问题
        """
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)