#!/usr/bin/env python3
"""
encode_secrets.py
─────────────────
Chạy script này MỘT LẦN trên máy local để tạo giá trị base64
cho GitHub Secrets.

Cách dùng:
python encode_secrets.py
"""

import base64, json, pathlib, sys

files = {
    'CREDENTIALS_JSON_B64':  'credentials.json',
    'INSTAGRAM_SESSION_B64': 'instagram_session.json',
}

print('=' * 60)
print('📋 Copy các giá trị sau vào GitHub Secrets:')
print('=' * 60)

for secret_name, filename in files.items():
    path = pathlib.Path(filename)
    if not path.exists():
        print(f'\n❌ Không tìm thấy file: {filename}')
        print(f'   Hãy đặt {filename} cùng thư mục với script này.')
        sys.exit(1)

    encoded = base64.b64encode(path.read_bytes()).decode('utf-8')
    print(f'\n── {secret_name} ──')
    print(encoded)

print('\n' + '=' * 60)
print('✅ Xong! Thêm thêm 2 secrets sau (không cần encode):')
print('   SHEET_ID    = <Google Sheet ID của bạn>')
print('   SHEET_NAME  = Sheet1')
print('=' * 60)
