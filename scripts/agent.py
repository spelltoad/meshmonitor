import json
import os
import platform
import socket
import subprocess
import time
import urllib.request
import urllib.error
import logging
import signal
import sys

COLLECTOR_HOST = "192.168.1.60"
COLLECTOR_URL = f"http://{COLLECTOR_HOST}:30080/api/v1/telemetry"

ROUTERS = {
    "router-main": "192.168.1.1",
    "router-secondary": "192.168.1.69"
}

EXTERNAL_WAN_TARGET = "77.88.8.8"
DNS_TEST_DOMAIN = "mos.ru"

NODE_NAME = platform.node()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("agent")

_shutdown = False

def _handle_shutdown(signum, frame):
    global _shutdown
    _shutdown = True

if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)

def test_l3_ping(target_ip):
    is_windows = platform.system().lower() == "windows"
    param = "-n" if is_windows else "-c"
    timeout_param = "-w" if is_windows else "-W"
    timeout_val = "1000" if is_windows else "1"
    
    cmd = ["ping", param, "1", timeout_param, timeout_val, target_ip]
    
    start_time = time.time()
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        latency = (time.time() - start_time) * 1000
        return result.returncode == 0, round(latency, 2)
    except Exception:
        return False, 0.0

def test_l4_tcp(target_ip, port):
    start_time = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((target_ip, port))
        latency = (time.time() - start_time) * 1000
        return True, round(latency, 2)
    except Exception:
        return False, 0.0
    finally:
        s.close()

def test_l7_dns(domain):
    start_time = time.time()
    try:
        socket.gethostbyname(domain)
        latency = (time.time() - start_time) * 1000
        return True, round(latency, 2)
    except Exception:
        return False, 0.0

def test_l7_http(target_url):
    start_time = time.time()
    try:
        req = urllib.request.Request(target_url, headers={'User-Agent': 'Mesh-Agent-v2'})
        with urllib.request.urlopen(req, timeout=1.5) as response:
            latency = (time.time() - start_time) * 1000
            return response.status == 200, round(latency, 2), ""
    except urllib.error.HTTPError as e:
        latency = (time.time() - start_time) * 1000
        return True, round(latency, 2), f"HTTP-{e.code}"
    except Exception as e:
        return False, 0.0, "Timeout/Refused"

def send_telemetry(payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(COLLECTOR_URL, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as response:
            if response.status in [200, 202]:
                return True
            else:
                return False
    except Exception:
        return False

def main():
    log.info("Agent is running on %s", NODE_NAME)

    try:
        while not _shutdown:
            try:
                for name, ip in ROUTERS.items():
                    is_up, latency = test_l3_ping(ip)
                    send_telemetry({
                        "source_machine": NODE_NAME, "destination_node": name,
                        "layer_tested": "L3", "latency_ms": latency, "is_up": is_up, "error_message": "" if is_up else "Ping lost"
                    })

                    is_http, http_lat, err = test_l7_http(f"http://{ip}")
                    send_telemetry({
                        "source_machine": NODE_NAME, "destination_node": f"{name}-web",
                        "layer_tested": "L7", "latency_ms": http_lat, "is_up": is_http, "error_message": err
                    })

                wan_up, wan_lat = test_l3_ping(EXTERNAL_WAN_TARGET)
                send_telemetry({
                    "source_machine": NODE_NAME, "destination_node": "internet-gateway",
                    "layer_tested": "L3", "latency_ms": wan_lat, "is_up": wan_up, "error_message": "" if wan_up else "ISP Outage"
                })

                k8s_up, k8s_lat = test_l4_tcp(COLLECTOR_HOST, 30080)
                send_telemetry({
                    "source_machine": NODE_NAME, "destination_node": "thinkpad-k3s-port",
                    "layer_tested": "L4", "latency_ms": k8s_lat, "is_up": k8s_up, "error_message": "" if k8s_up else "K3s port down"
                })

                ssh_up, ssh_lat = test_l4_tcp(COLLECTOR_HOST, 22)
                send_telemetry({
                    "source_machine": NODE_NAME, "destination_node": "thinkpad-ssh-port",
                    "layer_tested": "L4", "latency_ms": ssh_lat, "is_up": ssh_up, "error_message": "" if ssh_up else "OS freeze/SSH down"
                })

                dns_ok, dns_lat = test_l7_dns(DNS_TEST_DOMAIN)
                send_telemetry({
                    "source_machine": NODE_NAME, "destination_node": "dns-resolver",
                    "layer_tested": "L7", "latency_ms": dns_lat, "is_up": dns_ok, "error_message": "" if dns_ok else "DNS resolution failed"
                })

                log.info("Metrics sent to %s", COLLECTOR_HOST)
            except Exception:
                log.exception("Unhandled error in monitoring cycle, will retry after sleep")

            if _shutdown:
                break
            time.sleep(15)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Agent shutting down on %s", NODE_NAME)


if __name__ == "__main__":
    main()