import json
import socket
import threading
import time


HOST = "127.0.0.1"
PORT = 9000
CLIENT_COUNT = 50
MESSAGES_PER_CLIENT = 3
HOLD_SECONDS = 10
SOCKET_TIMEOUT = 5


stats = {
    "connected": 0,
    "login_success": 0,
    "messages_sent": 0,
    "online_list_success": 0,
    "failures": 0,
}
errors = []
stats_lock = threading.Lock()
start_event = threading.Event()


def send_json(sock, data):
    line = json.dumps(data, ensure_ascii=False) + "\n"
    sock.sendall(line.encode("utf-8"))


def recv_json(sock, pending, timeout=SOCKET_TIMEOUT):
    sock.settimeout(timeout)

    while True:
        newline_index = pending.find(b"\n")
        if newline_index >= 0:
            line = pending[:newline_index]
            del pending[: newline_index + 1]
            if not line:
                continue
            return json.loads(line.decode("utf-8"))

        chunk = sock.recv(4096)
        if not chunk:
            return None
        pending.extend(chunk)


def add_stat(name, amount=1):
    with stats_lock:
        stats[name] += amount


def record_failure(username, reason):
    with stats_lock:
        stats["failures"] += 1
        if len(errors) < 10:
            errors.append(f"{username}: {reason}")


def wait_for_message_type(sock, expected_type, timeout):
    deadline = time.time() + timeout
    pending = bytearray()

    while time.time() < deadline:
        try:
            message = recv_json(
                sock,
                pending,
                timeout=max(0.1, deadline - time.time()),
            )
        except socket.timeout:
            return None

        if message is None:
            return None
        if message.get("type") == expected_type:
            return message

    return None


def receive_loop(sock, stop_event, online_list_event):
    pending = bytearray()

    while not stop_event.is_set():
        try:
            message = recv_json(sock, pending, timeout=0.5)
        except socket.timeout:
            continue
        except (ConnectionResetError, OSError, ValueError):
            return

        if message is None:
            return
        if message.get("type") == "online_list":
            online_list_event.set()


def simulated_client(index):
    username = f"user_{index:03d}"
    sock = None
    stop_event = threading.Event()
    receiver = None

    start_event.wait()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((HOST, PORT))
        add_stat("connected")

        send_json(sock, {"type": "login", "username": username})
        login_response = wait_for_message_type(sock, "login_success", SOCKET_TIMEOUT)
        if login_response is None:
            record_failure(username, "login failed or timed out")
            return
        add_stat("login_success")

        online_list_event = threading.Event()
        receiver = threading.Thread(
            target=receive_loop,
            args=(sock, stop_event, online_list_event),
            daemon=True,
        )
        receiver.start()

        for message_index in range(1, MESSAGES_PER_CLIENT + 1):
            content = f"stress message {message_index} from {username}"
            send_json(sock, {"type": "chat", "content": content})
            add_stat("messages_sent")

        send_json(sock, {"type": "online_list"})
        time.sleep(HOLD_SECONDS)

        if not online_list_event.is_set():
            record_failure(username, "online list request timed out")
            return
        add_stat("online_list_success")

        send_json(sock, {"type": "quit"})
    except (ConnectionRefusedError, TimeoutError, socket.timeout) as exc:
        record_failure(username, f"network timeout/refused: {exc}")
    except (ConnectionResetError, OSError, ValueError, json.JSONDecodeError) as exc:
        record_failure(username, f"client error: {exc}")
    finally:
        stop_event.set()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if receiver is not None:
            receiver.join(timeout=1)


def main():
    threads = []
    start_time = time.time()

    for index in range(1, CLIENT_COUNT + 1):
        thread = threading.Thread(target=simulated_client, args=(index,))
        thread.start()
        threads.append(thread)

    start_event.set()

    for thread in threads:
        thread.join()

    elapsed = time.time() - start_time

    print("Stress test result")
    print(f"Target server: {HOST}:{PORT}")
    print(f"Total clients: {CLIENT_COUNT}")
    print(f"Successful connections: {stats['connected']}")
    print(f"Successful logins: {stats['login_success']}")
    print(f"Messages sent successfully: {stats['messages_sent']}")
    print(f"Online list responses: {stats['online_list_success']}")
    print(f"Failures: {stats['failures']}")
    print(f"Total elapsed time: {elapsed:.2f}s")

    if errors:
        print("Sample failures:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
