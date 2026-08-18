"""Parser tests: VLESS, Trojan, VMess, Shadowsocks, JSON, subscription detection."""

from backend.configs import parser

VLESS_URI = ("vless://550e8400-e29b-41d4-a716-446655440000@example.com:443"
             "?security=tls&sni=panel.example.com&fp=chrome&type=xhttp&host=cdn.example.com"
             "&path=/data&mode=cors&flow=xtls-rprx-vision&pbk=publickey123&sid=abcd"
             "&alpn=h2,http/1.1#RVG-Johnny")


def test_vless_uri():
    r = parser.parse_single(VLESS_URI)
    assert "error" not in r
    assert r["protocol"] == "vless"
    assert r["uuid"] == "550e8400-e29b-41d4-a716-446655440000"
    assert r["address"] == "example.com"
    assert r["port"] == 443
    assert r["security"] == "tls"
    assert r["sni"] == "panel.example.com"
    assert r["fingerprint"] == "chrome"
    assert r["network"] == "xhttp"
    assert r["host"] == "cdn.example.com"
    assert r["path"] == "/data"
    assert r["mode"] == "cors"
    assert r["public_key"] == "publickey123"
    assert r["short_id"] == "abcd"
    assert r["alpn"] == ["h2", "http/1.1"]
    assert r["name"] == "RVG-Johnny"


def test_vless_missing_uuid():
    r = parser.parse_single("vless://@example.com:443")
    assert r["error"]


def test_trojan_uri():
    r = parser.parse_single("trojan://s3cret@trojan.example.com:443?sni=trojan.example.com&fp=chrome#MyTrojan")
    assert r["protocol"] == "trojan"
    assert r["password"] == "s3cret"
    assert r["address"] == "trojan.example.com"
    assert r["port"] == 443
    assert r["sni"] == "trojan.example.com"
    assert r["name"] == "MyTrojan"


def test_trojan_missing_password():
    r = parser.parse_single("trojan://@host:443")
    assert r["error"]


def test_vmess_uri():
    import base64, json
    payload = json.dumps({"ps": "VMess-Test", "add": "vm.example.com", "port": "443",
                          "id": "550e8400-e29b-41d4-a716-446655440000", "net": "ws",
                          "host": "ws.example.com", "path": "/ws", "tls": "tls"})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    r = parser.parse_single(f"vmess://{encoded}#VMess-Test")
    assert r["protocol"] == "vmess"
    assert r["name"] == "VMess-Test"
    assert r["address"] == "vm.example.com"
    assert r["port"] == "443"
    assert r["uuid"] == "550e8400-e29b-41d4-a716-446655440000"


def test_shadowsocks_uri():
    import base64
    userinfo = base64.b64encode(b"aes-256-gcm:pass123").decode()
    r = parser.parse_single(f"ss://{userinfo}@ss.example.com:8388#SS-Test")
    assert r["protocol"] == "ss"
    assert r["method"] == "aes-256-gcm"
    assert r["password"] == "pass123"
    assert r["address"] == "ss.example.com"
    assert r["port"] == 8388


def test_parse_many():
    payload = VLESS_URI + "\n" + "trojan://pw@host2:443#T2"
    results = parser.parse_many(payload)
    assert len(results) == 2
    assert results[0]["protocol"] == "vless"
    assert results[1]["protocol"] == "trojan"


def test_subscription_url_detection():
    r = parser.parse_single("https://sub.example.com/v1/x?token=abc")
    assert r["source"] == "subscription"


def test_xray_json_config():
    xray = {
        "outbounds": [{
            "protocol": "vless",
            "settings": {"vnext": [{
                "address": "json.example.com", "port": 443,
                "users": [{"id": "550e8400-e29b-41d4-a716-446655440000", "flow": "xtls-rprx-vision"}],
            }]},
            "streamSettings": {"network": "ws", "security": "tls",
                               "tlsSettings": {"serverName": "json.example.com", "fingerprint": "chrome"}},
        }]
    }
    import json as jsonlib
    r = parser.parse_single(jsonlib.dumps(xray))
    assert r["protocol"] == "vless"
    assert r["address"] == "json.example.com"
    assert r["port"] == 443
    assert r["network"] == "ws"
    assert r["security"] == "tls"
    assert r["sni"] == "json.example.com"


def test_invalid_json():
    r = parser.parse_single("{not valid json")
    assert "error" in r


def test_unsupported_scheme():
    r = parser.parse_single("bogus://x")
    assert "error" in r
