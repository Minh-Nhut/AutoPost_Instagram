#!/usr/bin/env python3
"""
get_instagram_session.py
────────────────────────
Chuyển file cookies.json (export từ browser extension)
thành instagram_session.json dùng cho bot.

Cách dùng:
1. Cài extension "Cookie-Editor" trên Chrome/Firefox
2. Vào instagram.com, đăng nhập, mở extension → Export → JSON
3. Lưu file đó là cookies.json, đặt cùng thư mục với script này
4. Chạy: python get_instagram_session.py
"""

import json, os

COOKIES_PATH = "cookies.json"
SESSION_FILE = "instagram_session.json"

if not os.path.exists(COOKIES_PATH):
    print("❌ Không tìm thấy cookies.json")
    print("   Hãy export cookies từ instagram.com bằng Cookie-Editor extension")
else:
    with open(COOKIES_PATH, "r", encoding="utf-8") as f:
        cookies_list = json.load(f)

    pw_cookies = []
    for c in cookies_list:
        sameSite = c.get("sameSite", "Lax") or "Lax"
        if sameSite not in ["Strict", "Lax", "None"]:
            sameSite = "Lax"
        pw_cookie = {
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   c.get("domain", ".instagram.com"),
            "path":     c.get("path", "/"),
            "expires":  float(c.get("expirationDate", -1)),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure":   bool(c.get("secure", False)),
            "sameSite": sameSite,
        }
        pw_cookies.append(pw_cookie)

    session_data = {"cookies": pw_cookies, "origins": []}

    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Tạo session thành công: {SESSION_FILE}")
    print(f"   Tổng cookies: {len(pw_cookies)}")
    print(f"\n👉 Bước tiếp theo:")
    print(f"   1. Chạy encode_secrets.py để tạo base64")
    print(f"   2. Update secret INSTAGRAM_SESSION_B64 trên GitHub")
