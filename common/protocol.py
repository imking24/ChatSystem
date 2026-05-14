import json


def send_json(sock, data):
    """
    Send one JSON object using the JSON Lines protocol.

    Each message is encoded as UTF-8 JSON and terminated by a single newline.
    """
    line = json.dumps(data, ensure_ascii=False) + "\n"
    sock.sendall(line.encode("utf-8"))


def recv_json(sock):
    """
    Receive one JSON object using the JSON Lines protocol.

    Returns None when the peer closes the connection.
    """
    chunks = bytearray()

    while True:
        chunk = sock.recv(1)
        if not chunk:
            return None

        if chunk == b"\n":
            if not chunks:
                continue
            return json.loads(chunks.decode("utf-8"))

        chunks.extend(chunk)
