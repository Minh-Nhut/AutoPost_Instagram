#!/usr/bin/env python3
import os, time, json, base64
os.environ['TZ'] = 'Asia/Ho_Chi_Minh'
time.tzset()

SHEET_ID        = os.environ.get('SHEET_ID', '')
SHEET_NAME      = os.environ.get('SHEET_NAME', 'Sheet1')
INSTAGRAM_URL   = 'https://www.instagram.com'
CREDENTIALS_FILE = '/tmp/credentials.json'
SESSION_FILE     = '/tmp/instagram_session.json'

import subprocess, sys, random
from datetime import datetime, timedelta

print(f"⏰ Múi giờ: {time.strftime('%Z %z')}")
print(f"🕐 Giờ hiện tại: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

def restore_secrets():
    creds_b64 = os.environ.get('CREDENTIALS_JSON_B64', '')
    if not creds_b64:
        print('❌ Thiếu secret CREDENTIALS_JSON_B64')
        sys.exit(1)
    with open(CREDENTIALS_FILE, 'wb') as f:
        f.write(base64.b64decode(creds_b64))
    print(f'✅ Khôi phục credentials.json → {CREDENTIALS_FILE}')

    session_b64 = os.environ.get('INSTAGRAM_SESSION_B64', '')
    if not session_b64:
        print('❌ Thiếu secret INSTAGRAM_SESSION_B64')
        sys.exit(1)
    with open(SESSION_FILE, 'wb') as f:
        f.write(base64.b64decode(session_b64))
    print(f'✅ Khôi phục instagram_session.json → {SESSION_FILE}')

def connect_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def get_pending_posts(sheet):
    records = sheet.get_all_records(
        expected_headers=['content', 'image_url', 'hashtags', 'scheduled_time', 'status']
    )
    now = datetime.now()
    result = []
    for i, row in enumerate(records, start=2):
        status = str(row.get('status', '')).strip().lower()
        if status != 'pending':
            continue
        content = str(row.get('content', '')).strip()
        image_url = str(row.get('image_url', '')).strip()
        # Instagram bắt buộc phải có ảnh để đăng post ảnh
        if not image_url:
            print(f'⚠️ Row {i}: Không có image_url, bỏ qua (Instagram cần ảnh)')
            continue
        scheduled = str(row.get('scheduled_time', '')).strip()
        should_post = False
        if not scheduled:
            should_post = True
        else:
            try:
                scheduled_dt = datetime.strptime(scheduled, '%d/%m/%Y %H:%M')
                if now >= scheduled_dt - timedelta(minutes=5):
                    should_post = True
            except ValueError:
                print(f'⚠️ Row {i}: Sai định dạng thời gian: {scheduled}')
        if should_post:
            result.append({
                'row': i,
                'content': content,
                'image_url': image_url,
                'hashtags': str(row.get('hashtags', '')).strip(),
                'scheduled_time': scheduled
            })
    return result

def update_status(sheet, row_num, status, post_id=''):
    sheet.update_cell(row_num, 5, status)
    if post_id:
        sheet.update_cell(row_num, 6, post_id)
    sheet.update_cell(row_num, 7, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print(f'   📝 Cập nhật row {row_num}: {status}')

def _write_pw_worker():
    path = '/tmp/pw_worker.py'
    lines = [
        'import sys, json, random, time, os, re\n',
        'import urllib.request\n',
        'from playwright.sync_api import sync_playwright\n',
        '\n',
        'args          = json.loads(os.environ["PW_PAYLOAD"])\n',
        'content       = args["content"]\n',
        'image_url     = args.get("image_url", "")\n',
        'hashtags      = args.get("hashtags", "").strip()\n',
        'SESSION_FILE  = args["session_file"]\n',
        'INSTAGRAM_URL = args["instagram_url"]\n',
        '\n',
        'def log(msg): print(msg, flush=True)\n',
        '\n',
        'def get_direct_image_url(url):\n',
        '    if not url: return ""\n',
        '    m = re.search(r"/file/d/([^/]+)", url)\n',
        '    if m: return f"https://drive.google.com/uc?export=download&id={m.group(1)}"\n',
        '    m = re.search(r"[?&]id=([^&]+)", url)\n',
        '    if m: return f"https://drive.google.com/uc?export=download&id={m.group(1)}"\n',
        '    return url\n',
        '\n',
        'def download_image(url):\n',
        '    if not url: return None\n',
        '    try:\n',
        '        direct = get_direct_image_url(url)\n',
        '        log(f"   🖼️ Tải ảnh: {direct[:80]}")\n',
        '        dest = "/tmp/post_image.jpg"\n',
        '        req = urllib.request.Request(direct, headers={"User-Agent": "Mozilla/5.0"})\n',
        '        with urllib.request.urlopen(req, timeout=30) as resp:\n',
        '            with open(dest, "wb") as f:\n',
        '                f.write(resp.read())\n',
        '        size = os.path.getsize(dest)\n',
        '        log(f"   ✅ Tải ảnh xong ({size} bytes)")\n',
        '        return dest if size > 1000 else None\n',
        '    except Exception as e:\n',
        '        log(f"   ⚠️ Không tải được ảnh: {e}")\n',
        '        return None\n',
        '\n',
        'def dismiss_popups(page):\n',
        '    popup_sels = [\n',
        '        \'button:has-text("Allow")\',\n',
        '        \'button:has-text("Accept all")\',\n',
        '        \'button:has-text("Only allow essential cookies")\',\n',
        '        \'button:has-text("Not Now")\',\n',
        '        \'button:has-text("Không bây giờ")\',\n',
        '        \'button:has-text("Turn On Notifications")\',\n',
        '        \'button:has-text("Later")\',\n',
        '        \'button:has-text("Close")\',\n',
        '        \'[aria-label="Close"]\',\n',
        '    ]\n',
        '    for sel in popup_sels:\n',
        '        try:\n',
        '            btn = page.locator(sel).first\n',
        '            if btn.is_visible():\n',
        '                btn.click()\n',
        '                log(f"   🚫 Đóng popup: {sel}")\n',
        '                time.sleep(0.5)\n',
        '        except:\n',
        '            pass\n',
        '\n',
        'if not image_url:\n',
        '    log("ERR:NO_IMAGE")\n',
        '    sys.exit(6)\n',
        '\n',
        'if not os.path.exists(SESSION_FILE):\n',
        '    log("ERR:NO_SESSION")\n',
        '    sys.exit(1)\n',
        '\n',
        'local_image = download_image(image_url)\n',
        'if not local_image:\n',
        '    log("ERR:IMAGE_DOWNLOAD_FAILED")\n',
        '    sys.exit(6)\n',
        '\n',
        'INIT_SCRIPT = (\n',
        '    "Object.defineProperty(navigator, \\"webdriver\\", {get: () => undefined});"\n',
        '    " window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};"\n',
        '    " Object.defineProperty(navigator, \\"plugins\\", {get: () => [1,2,3,4,5]});"\n',
        '    " Object.defineProperty(navigator, \\"languages\\", {get: () => [\\"vi-VN\\",\\"vi\\",\\"en-US\\",\\"en\\"]});"\n',
        ')\n',
        '\n',
        '# Gộp caption + hashtags\n',
        'caption = content\n',
        'if hashtags:\n',
        '    caption = caption + "\\n\\n" + hashtags\n',
        '\n',
        'with sync_playwright() as p:\n',
        '    browser = p.chromium.launch(\n',
        '        headless=True,\n',
        '        args=["--no-sandbox", "--disable-dev-shm-usage",\n',
        '              "--disable-blink-features=AutomationControlled",\n',
        '              "--window-size=1280,800"]\n',
        '    )\n',
        '    context = browser.new_context(\n',
        '        storage_state=SESSION_FILE,\n',
        '        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",\n',
        '        viewport={"width": 1280, "height": 800},\n',
        '        locale="vi-VN",\n',
        '        timezone_id="Asia/Ho_Chi_Minh",\n',
        '    )\n',
        '    context.add_init_script(INIT_SCRIPT)\n',
        '    page = context.new_page()\n',
        '    try:\n',
        '        log("   🌐 Mở Instagram...")\n',
        '        # Dùng domcontentloaded thay networkidle — Instagram chặn networkidle trên cloud IP\n',
        '        for attempt in range(3):\n',
        '            try:\n',
        '                page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=60000)\n',
        '                break\n',
        '            except Exception as ge:\n',
        '                log(f"   ⚠️ goto attempt {attempt+1}/3 lỗi: {ge}")\n',
        '                if attempt == 2: raise\n',
        '                time.sleep(5)\n',
        '        time.sleep(random.uniform(3.0, 5.0))\n',
        '\n',
        '        log(f"   🔗 URL: {page.url}")\n',
        '        log(f"   📄 Title: {page.title()}")\n',
        '\n',
        '        if "login" in page.url or "accounts/login" in page.url:\n',
        '            page.screenshot(path="/tmp/debug_login.png")\n',
        '            log("ERR:SESSION_EXPIRED")\n',
        '            sys.exit(2)\n',
        '\n',
        '        log("   ✅ Đã đăng nhập Instagram")\n',
        '        dismiss_popups(page)\n',
        '        time.sleep(random.uniform(2.0, 3.0))\n',
        '\n',
        '        # ── DEBUG: Dump elements để biết aria-label thực tế ──\n',
        '        try:\n',
        '            nav_info = page.evaluate("""\n',
        '                () => {\n',
        '                    const els = Array.from(document.querySelectorAll("a,button,[role=\'button\'],svg"));\n',
        '                    return els.filter(e => e.offsetParent !== null).map(e => ({\n',
        '                        tag: e.tagName,\n',
        '                        aria: e.getAttribute("aria-label") || "",\n',
        '                        href: e.getAttribute("href") || "",\n',
        '                        text: (e.innerText || "").trim().slice(0, 30)\n',
        '                    })).filter(e => e.aria || e.href || e.text).slice(0, 50);\n',
        '                }\n',
        '            """)\n',
        '            log("   🔍 [DEBUG] Elements visible:")\n',
        '            for el in nav_info:\n',
        '                log(f\'      {el["tag"]} aria="{el["aria"]}" href="{el["href"]}" text="{el["text"]}"\')\n',
        '        except Exception as e:\n',
        '            log(f"   ⚠️ Không dump được: {e}")\n',
        '\n',
        '        page.screenshot(path="/tmp/debug_home.png")\n',
        '\n',
        '        # ── Bước 1: Click nút tạo bài mới ──\n',
        '        compose_clicked = False\n',
        '        compose_sels = [\n',
        '            \'svg[aria-label="Bài viết mới"]\',\n',
        '            \'[aria-label="Bài viết mới"]\',\n',
        '            \'svg[aria-label="New post"]\',\n',
        '            \'[aria-label="New post"]\',\n',
        '            \'[aria-label="Create"]\',\n',
        '            \'[aria-label="Tạo"]\',\n',
        '            \'svg[aria-label="Create"]\',\n',
        '            \'a[href="/create/select/"]\',\n',
        '            \'a[href*="/create"]\',\n',
        '        ]\n',
        '        for sel in compose_sels:\n',
        '            try:\n',
        '                el = page.locator(sel).first\n',
        '                el.wait_for(state="visible", timeout=3000)\n',
        '                # Nếu là SVG thì click vào thẻ A cha\n',
        '                if sel.startswith("svg"):\n',
        '                    el.locator("xpath=ancestor::a[1]").click()\n',
        '                else:\n',
        '                    el.click()\n',
        '                log(f"   🖱️ Click New Post: {sel}")\n',
        '                compose_clicked = True\n',
        '                break\n',
        '            except:\n',
        '                pass\n',
        '\n',
        '        # Fallback JS: click thẻ A chứa svg[aria-label="Bài viết mới"] hoặc các biến thể\n',
        '        if not compose_clicked:\n',
        '            try:\n',
        '                clicked = page.evaluate("""\n',
        '                    () => {\n',
        '                        const keywords = ["bài viết mới", "new post", "create", "tạo"];\n',
        '                        const svgs = Array.from(document.querySelectorAll("svg[aria-label]"));\n',
        '                        const svg = svgs.find(s => {\n',
        '                            const a = (s.getAttribute("aria-label") || "").toLowerCase();\n',
        '                            return keywords.some(k => a.includes(k));\n',
        '                        });\n',
        '                        if (!svg) return null;\n',
        '                        // Leo lên tìm thẻ A cha gần nhất\n',
        '                        let el = svg;\n',
        '                        for (let i = 0; i < 6; i++) {\n',
        '                            el = el.parentElement;\n',
        '                            if (!el) break;\n',
        '                            if (el.tagName === "A" || el.getAttribute("role") === "button") {\n',
        '                                el.click();\n',
        '                                return svg.getAttribute("aria-label");\n',
        '                            }\n',
        '                        }\n',
        '                        svg.click();\n',
        '                        return "svg-direct-click";\n',
        '                    }\n',
        '                """)\n',
        '                if clicked:\n',
        '                    log(f"   🖱️ JS fallback compose: {clicked}")\n',
        '                    compose_clicked = True\n',
        '            except Exception as e:\n',
        '                log(f"   ⚠️ JS compose lỗi: {e}")\n',
        '\n',
        '        if not compose_clicked:\n',
        '            log("ERR:NO_COMPOSE_BUTTON")\n',
        '            page.screenshot(path="/tmp/debug_no_compose.png")\n',
        '            sys.exit(3)\n',
        '\n',
        '        time.sleep(random.uniform(2.5, 3.5))\n',
        '        dismiss_popups(page)\n',
        '        page.screenshot(path="/tmp/debug_after_compose.png")\n',
        '        log("   📸 Screenshot sau click compose: /tmp/debug_after_compose.png")\n',
        '\n',
        '        # DEBUG: dump elements sau khi click compose\n',
        '        try:\n',
        '            els = page.evaluate("""\n',
        '                () => {\n',
        '                    const tags = ["button","input","[role=\'button\']","[role=\'dialog\'] *"];\n',
        '                    return Array.from(document.querySelectorAll("button,input,[role=\'button\']"))\n',
        '                        .filter(e => e.offsetParent !== null)\n',
        '                        .map(e => ({\n',
        '                            tag: e.tagName,\n',
        '                            type: e.getAttribute("type") || "",\n',
        '                            aria: e.getAttribute("aria-label") || "",\n',
        '                            text: (e.innerText || "").trim().slice(0, 40),\n',
        '                            accept: e.getAttribute("accept") || ""\n',
        '                        })).slice(0, 30);\n',
        '                }\n',
        '            """)\n',
        '            log("   🔍 [DEBUG] Elements sau compose click:")\n',
        '            for el in els:\n',
        '                log(f\'      {el["tag"]} type="{el["type"]}" aria="{el["aria"]}" text="{el["text"]}" accept="{el["accept"]}"\')\n',
        '        except Exception as e:\n',
        '            log(f"   ⚠️ Không dump được: {e}")\n',
        '\n',
        '        # ── Bước 2: Upload ảnh ──\n',
        '        log("   📂 Upload ảnh...")\n',
        '        upload_done = False\n',
        '\n',
        '        # Cách 1: input[type=file] — dùng page.set_input_files thay vì .count()\n',
        '        try:\n',
        '            file_input = page.locator(\'input[type="file"]\').first\n',
        '            file_input.wait_for(state="attached", timeout=5000)\n',
        '            page.set_input_files(\'input[type="file"]\', local_image)\n',
        '            log("   ✅ Upload qua input[type=file]")\n',
        '            upload_done = True\n',
        '        except Exception as e:\n',
        '            log(f"   ⚠️ input[type=file] lỗi: {e}")\n',
        '\n',
        '        # Cách 2: expect_file_chooser khi click nút\n',
        '        if not upload_done:\n',
        '            btn_sels = [\n',
        '                \'button:has-text("Chọn từ máy tính")\',\n',
        '                \'button:has-text("Select from computer")\',\n',
        '                \'button:has-text("Chọn")\',\n',
        '                \'button:has-text("Select")\',\n',
        '                \'[role="button"]:has-text("Chọn từ máy tính")\',\n',
        '                \'[role="button"]:has-text("Select from computer")\',\n',
        '                \'[role="button"]:has-text("Chọn")\',\n',
        '                \'svg[aria-label="Phương tiện"]\',\n',
        '                \'svg[aria-label="Media"]\',\n',
        '            ]\n',
        '            for sel in btn_sels:\n',
        '                try:\n',
        '                    btn = page.locator(sel).first\n',
        '                    btn.wait_for(state="visible", timeout=4000)\n',
        '                    with page.expect_file_chooser(timeout=6000) as fc_info:\n',
        '                        btn.click()\n',
        '                    fc_info.value.set_files(local_image)\n',
        '                    log(f"   ✅ Upload qua file chooser: {sel}")\n',
        '                    upload_done = True\n',
        '                    break\n',
        '                except:\n',
        '                    pass\n',
        '\n',
        '        # Cách 3: JS click vào input[type=file] ẩn rồi intercept file chooser\n',
        '        if not upload_done:\n',
        '            try:\n',
        '                with page.expect_file_chooser(timeout=6000) as fc_info:\n',
        '                    page.evaluate("() => { const i = document.querySelector(\'input[type=\\\"file\\\"]\'); if(i) i.click(); }")\n',
        '                fc_info.value.set_files(local_image)\n',
        '                log("   ✅ Upload qua JS click input file")\n',
        '                upload_done = True\n',
        '            except Exception as e:\n',
        '                log(f"   ⚠️ JS click file input lỗi: {e}")\n',
        '\n',
        '        if not upload_done:\n',
        '            page.screenshot(path="/tmp/debug_no_upload.png")\n',
        '            log("ERR:UPLOAD_FAILED")\n',
        '            sys.exit(6)\n',
        '\n',
        '        time.sleep(random.uniform(3.0, 5.0))\n',
        '        page.screenshot(path="/tmp/debug_after_upload.png")\n',
        '        log("   📸 Screenshot sau upload: /tmp/debug_after_upload.png")\n',
        '\n',
        '        # ── Bước 3: Bấm "Tiếp" 3 lần (Cắt → Chỉnh sửa → Caption) ──\n',
        '        def click_tiep(page, step_name):\n',
        '            """Click nút Tiếp, trả về True nếu thành công"""\n',
        '            # Đợi nút "Tiếp" xuất hiện\n',
        '            time.sleep(random.uniform(2.0, 3.0))\n',
        '            try:\n',
        '                clicked = page.evaluate("""\n',
        '                    () => {\n',
        '                        const btns = Array.from(document.querySelectorAll("button,[role=\'button\']"));\n',
        '                        const t = btns.find(b => {\n',
        '                            if (b.offsetParent === null || b.disabled) return false;\n',
        '                            const aria = (b.getAttribute("aria-label") || "").trim();\n',
        '                            const txt = (b.innerText || b.textContent || "").trim();\n',
        '                            return aria === "Tiếp" || aria === "Next" || txt === "Tiếp" || txt === "Next";\n',
        '                        });\n',
        '                        if (t) { t.click(); return t.getAttribute("aria-label") || t.innerText || "ok"; }\n',
        '                        return null;\n',
        '                    }\n',
        '                """)\n',
        '                if clicked:\n',
        '                    log(f"   ✅ Click Tiếp ({step_name}): {clicked}")\n',
        '                    return True\n',
        '            except Exception as e:\n',
        '                log(f"   ⚠️ JS Tiếp lỗi ({step_name}): {e}")\n',
        '            # Playwright fallback\n',
        '            for sel in [\'[aria-label="Tiếp"]\', \'[aria-label="Next"]\', \'button:has-text("Tiếp")\', \'button:has-text("Next")\']:\n',
        '                try:\n',
        '                    btn = page.locator(sel).first\n',
        '                    btn.wait_for(state="visible", timeout=4000)\n',
        '                    btn.click()\n',
        '                    log(f"   ✅ Click Tiếp ({step_name}) PW: {sel}")\n',
        '                    return True\n',
        '                except:\n',
        '                    pass\n',
        '            log(f"   ⚠️ Không tìm được Tiếp ({step_name})")\n',
        '            return False\n',
        '\n',
        '        # ── Bước 3a: Ở màn Cắt — chọn tỷ lệ "Gốc" trước khi bấm Tiếp ──\n',
        '        time.sleep(random.uniform(1.5, 2.5))\n',
        '        try:\n',
        '            selected_ratio = page.evaluate("""\n',
        '                () => {\n',
        '                    // Tìm nút "Gốc" / "Original" trong panel tỷ lệ\n',
        '                    const btns = Array.from(document.querySelectorAll("button,[role=\'button\'],span,div"));\n',
        '                    const t = btns.find(b => {\n',
        '                        if (b.offsetParent === null) return false;\n',
        '                        const txt = (b.innerText || b.textContent || "").trim();\n',
        '                        const aria = (b.getAttribute("aria-label") || "").trim();\n',
        '                        return txt === "Gốc" || txt === "Original" || aria === "Gốc" || aria === "Original";\n',
        '                    });\n',
        '                    if (t) { t.click(); return t.innerText || t.getAttribute("aria-label") || "clicked"; }\n',
        '                    return null;\n',
        '                }\n',
        '            """)\n',
        '            if selected_ratio:\n',
        '                log(f"   ✅ Đã chọn tỷ lệ: {selected_ratio}")\n',
        '            else:\n',
        '                log("   ℹ️ Không tìm thấy nút Gốc — có thể chưa mở panel crop hoặc đã mặc định")\n',
        '                # Thử click icon crop để mở panel rồi chọn Gốc\n',
        '                for crop_sel in [\'[aria-label="Chọn tỷ lệ cắt"]\', \'[aria-label="Select crop"]\', \'[aria-label="Crop"]\', \'svg[aria-label*="crop" i]\']:\n',
        '                    try:\n',
        '                        page.locator(crop_sel).first.click(timeout=2000)\n',
        '                        time.sleep(1)\n',
        '                        page.evaluate("""\n',
        '                            () => {\n',
        '                                const btns = Array.from(document.querySelectorAll("button,[role=\'button\'],span,div"));\n',
        '                                const t = btns.find(b => {\n',
        '                                    const txt = (b.innerText || b.textContent || "").trim();\n',
        '                                    return txt === "Gốc" || txt === "Original";\n',
        '                                });\n',
        '                                if (t) t.click();\n',
        '                            }\n',
        '                        """)\n',
        '                        log(f"   ✅ Mở crop panel và chọn Gốc qua: {crop_sel}")\n',
        '                        break\n',
        '                    except:\n',
        '                        pass\n',
        '        except Exception as e:\n',
        '            log(f"   ⚠️ Chọn tỷ lệ lỗi: {e}")\n',
        '\n',
        '        time.sleep(random.uniform(1.0, 1.5))\n',
        '        page.screenshot(path="/tmp/debug_crop_selected.png")\n',
        '        log("   📸 Sau chọn tỷ lệ: /tmp/debug_crop_selected.png")\n',
        '\n',
        '        # Bước Cắt → Chỉnh sửa\n',
        '        click_tiep(page, "Cắt→Chỉnh sửa")\n',
        '        page.screenshot(path="/tmp/debug_step_chinh_sua.png")\n',
        '        log("   📸 Bước Chỉnh sửa: /tmp/debug_step_chinh_sua.png")\n',
        '\n',
        '        # Bước Chỉnh sửa → Caption\n',
        '        click_tiep(page, "Chỉnh sửa→Caption")\n',
        '        time.sleep(random.uniform(2.5, 3.5))\n',
        '        page.screenshot(path="/tmp/debug_caption_step.png")\n',
        '        log("   📸 Bước Caption: /tmp/debug_caption_step.png")\n',
        '\n',
        '        # ── Bước 4: Nhập caption — đợi ô caption xuất hiện ──\n',
        '        caption_typed = False\n',
        '        # Thử nhiều selector, ưu tiên aria-label chính xác\n',
        '        caption_sels = [\n',
        '            \'[aria-label="Viết chú thích..."]\',\n',
        '            \'[aria-label="Write a caption..."]\',\n',
        '            \'[placeholder="Viết chú thích..."]\',\n',
        '            \'[placeholder="Write a caption..."]\',\n',
        '            \'div[role="textbox"][contenteditable="true"]\',\n',
        '            \'[contenteditable="true"]\',\n',
        '            \'div[role="textbox"]\',\n',
        '            \'textarea[placeholder*="chú thích"]\',\n',
        '            \'textarea[placeholder*="caption"]\',\n',
        '        ]\n',
        '        for sel in caption_sels:\n',
        '            try:\n',
        '                el = page.locator(sel).first\n',
        '                el.wait_for(state="visible", timeout=8000)\n',
        '                el.scroll_into_view_if_needed()\n',
        '                el.click()\n',
        '                time.sleep(0.8)\n',
        '                # Xóa nội dung cũ nếu có\n',
        '                el.press("Control+a")\n',
        '                time.sleep(0.3)\n',
        '                page.keyboard.type(caption, delay=random.randint(40, 80))\n',
        '                time.sleep(0.5)\n',
        '                # Kiểm tra đã gõ được chưa\n',
        '                typed_val = page.evaluate(f"""\n',
        '                    () => {{\n',
        '                        const el = document.querySelector(\'{sel}\');\n',
        '                        return el ? (el.innerText || el.value || el.textContent || "").trim() : "";\n',
        '                    }}\n',
        '                """)\n',
        '                if typed_val and len(typed_val) > 0:\n',
        '                    log(f"   ✅ Gõ caption xong ({len(caption)} ký tự) via {sel}")\n',
        '                    caption_typed = True\n',
        '                    break\n',
        '                else:\n',
        '                    # Thử JS setValue\n',
        '                    page.evaluate(f"""\n',
        '                        () => {{\n',
        '                            const el = document.querySelector(\'{sel}\');\n',
        '                            if (!el) return;\n',
        '                            el.focus();\n',
        '                            document.execCommand("selectAll", false, null);\n',
        '                            document.execCommand("insertText", false, {json.dumps(caption)});\n',
        '                        }}\n',
        '                    """)\n',
        '                    time.sleep(0.5)\n',
        '                    log(f"   ✅ Gõ caption qua execCommand ({len(caption)} ký tự) via {sel}")\n',
        '                    caption_typed = True\n',
        '                    break\n',
        '            except:\n',
        '                pass\n',
        '\n',
        '        if not caption_typed:\n',
        '            # Fallback cuối: JS tìm bất kỳ contenteditable trong dialog\n',
        '            try:\n',
        '                result = page.evaluate(f"""\n',
        '                    () => {{\n',
        '                        const els = Array.from(document.querySelectorAll(\'[contenteditable="true"], div[role="textbox"], textarea\'));\n',
        '                        const el = els.find(e => e.offsetParent !== null);\n',
        '                        if (!el) return false;\n',
        '                        el.focus();\n',
        '                        document.execCommand("selectAll", false, null);\n',
        '                        document.execCommand("insertText", false, {json.dumps(caption)});\n',
        '                        return true;\n',
        '                    }}\n',
        '                """)\n',
        '                if result:\n',
        '                    log(f"   ✅ Gõ caption qua JS fallback ({len(caption)} ký tự)")\n',
        '                    caption_typed = True\n',
        '            except Exception as e:\n',
        '                log(f"   ⚠️ JS caption fallback lỗi: {e}")\n',
        '\n',
        '        if not caption_typed:\n',
        '            log("   ⚠️ Không tìm được ô caption, đăng không có caption")\n',
        '\n',
        '        time.sleep(random.uniform(2.0, 3.0))\n',
        '        page.screenshot(path="/tmp/debug_before_share.png")\n',
        '\n',
        '        # DEBUG buttons\n',
        '        try:\n',
        '            btn_info = page.evaluate("""\n',
        '                () => Array.from(document.querySelectorAll("button,[role=\'button\']")).map(b => ({\n',
        '                    text: (b.innerText || b.textContent || "").trim().slice(0, 40),\n',
        '                    aria: b.getAttribute("aria-label") || "",\n',
        '                    visible: b.offsetParent !== null,\n',
        '                    disabled: b.disabled\n',
        '                })).filter(b => b.visible)\n',
        '            """)\n',
        '            log("   🔍 [DEBUG] Buttons trước Share:")\n',
        '            for bi in btn_info:\n',
        '                log(f\'      text="{bi["text"]}" aria="{bi["aria"]}" disabled={bi["disabled"]}\')\n',
        '        except Exception as e:\n',
        '            log(f"   ⚠️ Không dump buttons: {e}")\n',
        '\n',
        '        # ── Bước 5: Click "Chia sẻ" — retry tối đa 3 lần, chờ nút enabled ──\n',
        '        posted = False\n',
        '        for share_attempt in range(3):\n',
        '            if share_attempt > 0:\n',
        '                log(f"   🔄 Retry Share lần {share_attempt+1}...")\n',
        '                time.sleep(3)\n',
        '            # JS click — tìm nút Chia sẻ/Share không bị disabled\n',
        '            try:\n',
        '                clicked = page.evaluate("""\n',
        '                    () => {\n',
        '                        const btns = Array.from(document.querySelectorAll("button,[role=\'button\']"));\n',
        '                        const t = btns.find(b => {\n',
        '                            if (b.offsetParent === null || b.disabled) return false;\n',
        '                            const txt = (b.innerText || b.textContent || "").trim();\n',
        '                            const aria = (b.getAttribute("aria-label") || "").trim();\n',
        '                            return txt === "Chia sẻ" || txt === "Share"\n',
        '                                || aria === "Chia sẻ" || aria === "Share";\n',
        '                        });\n',
        '                        if (t) { t.click(); return t.getAttribute("aria-label") || t.innerText || "clicked"; }\n',
        '                        return null;\n',
        '                    }\n',
        '                """)\n',
        '                if clicked:\n',
        '                    posted = True\n',
        '                    log(f"   🚀 Click Chia sẻ JS: {clicked}")\n',
        '                    break\n',
        '            except Exception as e:\n',
        '                log(f"   ⚠️ JS Share lỗi: {e}")\n',
        '            # Playwright fallback\n',
        '            for sel in [\'button:has-text("Chia sẻ")\', \'button:has-text("Share")\', \'[aria-label="Chia sẻ"]\', \'[aria-label="Share"]\']:\n',
        '                try:\n',
        '                    btn = page.locator(sel).last\n',
        '                    btn.wait_for(state="visible", timeout=5000)\n',
        '                    # Đợi nút không còn disabled\n',
        '                    for _ in range(10):\n',
        '                        if not btn.is_disabled():\n',
        '                            break\n',
        '                        time.sleep(0.5)\n',
        '                    btn.click(force=True)\n',
        '                    posted = True\n',
        '                    log(f"   🚀 Click Chia sẻ PW: {sel}")\n',
        '                    break\n',
        '                except Exception as e:\n',
        '                    log(f"      {sel}: lỗi {e}")\n',
        '            if posted:\n',
        '                break\n',
        '\n',
        '        if not posted:\n',
        '            page.screenshot(path="/tmp/debug_no_share_btn.png")\n',
        '            log("ERR:NO_SHARE_BTN")\n',
        '            sys.exit(4)\n',
        '\n',
        '        # ── Chờ xác nhận ──\n',
        '        log("   ⏳ Chờ xác nhận bài đã đăng...")\n',
        '        time.sleep(10)\n',
        '        page.screenshot(path="/tmp/debug_after_post.png")\n',
        '        log(f"   📸 Screenshot sau đăng: /tmp/debug_after_post.png")\n',
        '        log(f"   🔗 URL sau đăng: {page.url}")\n',
        '\n',
        '        # Kiểm tra lỗi UI\n',
        '        for err_sel in [\n',
        '            \'[role="alert"]\',\n',
        '            \'div:has-text("Something went wrong")\',\n',
        '            \'div:has-text("Đã xảy ra lỗi")\',\n',
        '        ]:\n',
        '            try:\n',
        '                el = page.locator(err_sel).first\n',
        '                if el.is_visible():\n',
        '                    log(f"   ❌ Phát hiện lỗi: {err_sel}")\n',
        '                    log("ERR:POST_FAILED_UI_ERROR")\n',
        '                    sys.exit(7)\n',
        '            except:\n',
        '                pass\n',
        '\n',
        '        context.storage_state(path=SESSION_FILE)\n',
        '        post_id = "ig_" + str(int(time.time()))\n',
        '        if "/p/" in page.url or "instagram.com/@" in page.url:\n',
        '            post_id = page.url\n',
        '            log(f"   ✅ Xác nhận URL bài đăng: {post_id}")\n',
        '        else:\n',
        '            log(f"   ⚠️ URL sau đăng: {page.url}")\n',
        '        log(f"OK:{post_id}")\n',
        '        browser.close()\n',
        '\n',
        '    except Exception as e:\n',
        '        import traceback\n',
        '        traceback.print_exc()\n',
        '        try: page.screenshot(path="/tmp/err_exception.png")\n',
        '        except: pass\n',
        '        log(f"ERR:EXCEPTION:{str(e)[:150]}")\n',
        '        browser.close()\n',
        '        sys.exit(5)\n',
    ]
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return path

def post_to_instagram_browser(content, image_url='', hashtags=''):
    if not image_url:
        print('❌ Thiếu image_url! Instagram cần ảnh để đăng.')
        return None

    pw_worker = _write_pw_worker()
    env = os.environ.copy()
    env['PW_PAYLOAD'] = json.dumps({
        'content':      content,
        'image_url':    image_url,
        'hashtags':     hashtags,
        'session_file': SESSION_FILE,
        'instagram_url': INSTAGRAM_URL,
    })

    result = subprocess.run(
        [sys.executable, pw_worker],
        capture_output=True, text=True, encoding='utf-8',
        timeout=180, env=env
    )

    for line in result.stdout.splitlines():
        if line.startswith('OK:'):
            print(f'   ✅ Đăng thành công: {line[3:]}')
            return line[3:]
        else:
            print(line)

    if result.stderr:
        print('--- stderr ---')
        print(result.stderr[-1000:])
    return None

def process_and_post(sheet, post_data):
    row       = post_data['row']
    content   = post_data['content']
    image_url = post_data['image_url']
    hashtags  = post_data['hashtags']

    print(f'\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print(f'📌 Xử lý bài post (row {row}):')
    print(f'   Nội dung: {content[:80]}...' if len(content) > 80 else f'   Nội dung: {content}')
    print(f'   Ảnh: {image_url[:60]}...' if len(image_url) > 60 else f'   Ảnh: {image_url}')

    post_id = post_to_instagram_browser(content, image_url, hashtags)

    if post_id:
        update_status(sheet, row, 'done', str(post_id))
        print('✅ Đăng bài thành công!')
    else:
        update_status(sheet, row, 'error')
        print('❌ Đăng bài thất bại!')
        sys.exit(1)

    wait_sec = random.randint(30, 60)
    print(f'   ⏳ Chờ {wait_sec}s trước bài kế tiếp...')
    time.sleep(wait_sec)

if __name__ == '__main__':
    print('\n🤖 Instagram AutoPost Bot (GitHub Actions mode) đang khởi động...')
    restore_secrets()

    try:
        sheet = connect_sheet()
        posts = get_pending_posts(sheet)
        if not posts:
            print('📭 Không có bài nào cần đăng lúc này.')
            sys.exit(0)
        print(f'📋 Tìm thấy {len(posts)} bài cần đăng')
        for post in posts:
            process_and_post(sheet, post)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'❌ Lỗi: {e}')
        sys.exit(1)

    print(f'\n✅ Hoàn thành lúc {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')