import asyncio
import logging

class BrowserBot:
    def __init__(self, port="9222", mode="Create Image", model="Nano Banana 2", ratio="16:9", input_method="Paste"):
        self.port = port
        self.mode = mode
        self.model = model
        self.ratio = ratio
        self.input_method = input_method
        self.playwright = None
        self.browser = None
        self.is_cdp = False
        
    def _cleanup_profile_locks(self, profile_dir):
        import os, subprocess, shutil
        lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]
        for lock in lock_files:
            p = os.path.join(profile_dir, lock)
            if os.path.lexists(p):
                try:
                    if os.path.islink(p) or os.path.isfile(p):
                        os.unlink(p)
                    elif os.path.isdir(p):
                        shutil.rmtree(p)
                except Exception:
                    pass

    async def connect(self, log_callback=print):
        try:
            import asyncio, socket, os, subprocess, shutil
            from playwright.async_api import async_playwright
            log_callback(f"Initializing Playwright browser controller (Port {self.port})...")
            self.playwright = await async_playwright().start()

            is_listening = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    if s.connect_ex(('127.0.0.1', int(self.port))) == 0:
                        is_listening = True
            except Exception:
                pass

            if not is_listening:
                log_callback(f"🚀 Chrome chưa chạy. Đang mở Chrome Debug port {self.port}...")
                profile_dir = os.path.expanduser(f"~/.gemini/antigravity/scratch/chrome_debug_profile_{self.port}")
                for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
                    p = os.path.join(profile_dir, lock)
                    if os.path.lexists(p):
                        try:
                            if os.path.islink(p) or os.path.isfile(p): os.unlink(p)
                            elif os.path.isdir(p): shutil.rmtree(p)
                        except Exception: pass
                cmd = [
                    "open", "-n", "-a", "Google Chrome", "--args",
                    f"--remote-debugging-port={self.port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--process-per-site",                  # Gộp các tab Google Flow dùng chung 1 tiến trình -> Tiết kiệm 60% RAM
                    "--js-flags=--max-old-space-size=512", # Giới hạn Heap 512MB để ép V8 Engine dọn rác bộ nhớ (GC) liên tục
                    "--enable-low-end-device-mode",        # Ép Chrome kích hoạt chế độ tối ưu hóa bộ nhớ RAM cao cấp
                    "--disable-background-networking",     # Tắt tải ngầm không cần thiết
                    "--disable-component-update",
                    "--disable-breakpad",
                    "--disable-features=Translate,OptimizationHints,MediaRouter",
                    "https://labs.google/fx/vi/tools/flow"
                ]
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    log_callback(f"❌ Không thể mở Chrome: {e}")
                    return False
                log_callback("⏳ Đang đợi Chrome khởi động tối đa 20 giây...")

            log_callback(f"Đang kết nối CDP tới port {self.port}...")
            last_error = None
            for attempt in range(20):
                try:
                    self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
                    self.is_cdp = True
                    log_callback(f"✅ Connected to Chrome debug instance (port {self.port}).")
                    return True
                except Exception as e:
                    last_error = e
                    if attempt < 19:
                        await asyncio.sleep(1)
                    continue

            log_callback(f"❌ Không thể kết nối CDP. Lỗi cuối: {last_error}")
            return False
        except Exception as e:
            log_callback(f"Failed to connect browser: {e}")
            return False

    async def initialize_tab_pool(self, max_tabs, log_callback=print, is_running_func=None):
        """Khởi tạo sẵn N tab song song trong phòng Studio trước khi chạy tác vụ"""
        context = self.browser.contexts[0] if (self.browser and hasattr(self.browser, 'contexts') and self.browser.contexts) else None
        if not context:
            return False
            
        log_callback(f"🚀 Đang chuẩn bị {max_tabs} tab song song trong Google Flow...")
        
        # 1. Đảm bảo Tab 1 đã vào phòng dự án
        first_page = context.pages[0] if context.pages else await context.new_page()
        if "project" not in first_page.url:
            await first_page.goto("https://labs.google/fx/vi/tools/flow", timeout=30000)
            await self.ensure_logged_in_and_in_project(first_page, 1, log_callback, is_running_func)
            
        project_url = first_page.url if "project" in first_page.url else "https://labs.google/fx/vi/tools/flow"
        self.current_project_url = project_url
        
        # 2. Mở thêm cho đủ max_tabs ngay tại project_url
        existing_pages = [p for p in context.pages if not p.is_closed()]
        needed = max_tabs - len(existing_pages)
        if needed > 0:
            log_callback(f"📑 Đang mở đồng loạt {needed} tab để tạo ảnh song song...")
            for i in range(needed):
                if is_running_func and not is_running_func():
                    break
                new_p = await context.new_page()
                await new_p.goto(project_url, timeout=30000)
                await asyncio.sleep(0.5)
                
        self.available_pages = [p for p in context.pages if not p.is_closed()]
        log_callback(f"✅ Đã kích hoạt xong {len(self.available_pages)} tab song song độc lập!")
        return True
            
    def kill_chrome(self, log_callback=print):
        """Immediately kill all Chrome debug processes and tabs on port self.port."""
        import subprocess, os
        log_callback(f"💥 Đang kill lập tức tất cả tab Chrome đang chạy (Port {self.port})...")
        
        self.available_pages = []

        try:
            subprocess.run(f"pkill -9 -f 'remote-debugging-port={self.port}'", shell=True, check=False)
            subprocess.run(f"pkill -9 -f 'chrome_debug_profile_{self.port}'", shell=True, check=False)
        except Exception as e:
            log_callback(f"⚠️ Lỗi khi kill Chrome: {e}")

        profile_dir = os.path.expanduser(f"~/.gemini/antigravity/scratch/chrome_debug_profile_{self.port}")
        self._cleanup_profile_locks(profile_dir)
        
        self.browser = None
        self.playwright = None
        log_callback("✅ Đã kill toàn bộ tab/tiến trình Chrome.")

    async def disconnect(self, log_callback=print):
        if self.playwright:
            try: await self.playwright.stop()
            except: pass
            
        self.kill_chrome(log_callback=log_callback)
        log_callback("Disconnected from Chrome.")

    async def select_model_on_page(self, page, target_model, task_id, log_callback=print):
        try:
            trigger = page.locator('button, [role="button"], span, div').filter(has_text="Banana").or_(
                page.locator('button, [role="button"], span, div').filter(has_text="Nano"))
            count = await trigger.count()
            for i in reversed(range(count)):
                el = trigger.nth(i)
                try:
                    if await el.is_visible():
                        box = await el.bounding_box()
                        txt = (await el.inner_text()).strip()
                        if box and 50 < (box['width'] * box['height']) < 25000 and len(txt) < 50:
                            current_txt = txt
                            if target_model.lower() in current_txt.lower():
                                return True
                            await el.click()
                            await asyncio.sleep(1.5)
                            opt = page.get_by_text(target_model, exact=False).first
                            if await opt.is_visible():
                                await opt.click()
                                log_callback(f"[Task {task_id}] ✅ Đã chọn model '{target_model}' trên giao diện.")
                                await asyncio.sleep(2)
                                return True
                            menu_items = await page.locator('div[role="menuitem"], div[role="option"], li, button, span').all()
                            for item in menu_items:
                                txt2 = await item.inner_text()
                                if target_model.lower() in txt2.lower():
                                    await item.click()
                                    log_callback(f"[Task {task_id}] ✅ Đã chọn model '{txt2.strip()}'.")
                                    await asyncio.sleep(2)
                                    return True
                except:
                    pass
            log_callback(f"[Task {task_id}] ⚠️ Không tìm thấy model trigger để chọn '{target_model}'.")
        except Exception as e:
            log_callback(f"[Task {task_id}] Lỗi chọn model: {e}")
        return False

    async def check_and_switch_model_if_limit_reached(self, page, task_id, log_callback=print):
        """Kiểm tra xem trang Google Flow có hiển thị thông báo chạm hạn mức (quota limit) hay không"""
        try:
            body_text = await page.evaluate("() => document.body.innerText || ''")
            body_text_lower = body_text.lower()
            
            limit_keywords = [
                "dùng hết hạn mức", "hạn mức về số lượt tạo", "đạt đến giới hạn",
                "dùng một mô hình khác", "thử dùng một mô hình khác",
                "quota exceeded", "rate limit", "too many requests"
            ]
            
            if any(kw in body_text_lower for kw in limit_keywords):
                log_callback(f"[Task {task_id}] ⚠️ Phát hiện thông báo hết hạn mức lượt tạo trên Google Flow!")
                
                models = ["Nano Banana 2", "Nano Banana Pro", "Nano Banana Lite"]
                current_model_clean = self.model.strip()
                
                next_model = "Nano Banana Pro"
                for idx, m in enumerate(models):
                    if m.lower() in current_model_clean.lower():
                        next_model = models[(idx + 1) % len(models)]
                        break
                        
                log_callback(f"[Task {task_id}] 🔄 Đang tự động đổi từ model '{self.model}' sang model tiếp theo: '{next_model}'...")
                self.model = next_model
                
                # Bấm nút mở menu chọn model ở góc dưới giao diện Google Flow
                clicked_dropdown = False
                try:
                    model_trigger = page.locator('button, [role="button"], span, div').filter(has_text="Banana").or_(page.locator('button, [role="button"], span, div').filter(has_text="Nano"))
                    count = await model_trigger.count()
                    for i in reversed(range(count)):
                        el = model_trigger.nth(i)
                        try:
                            if await el.is_visible():
                                box = await el.bounding_box()
                                txt = (await el.inner_text()).strip()
                                if box and 50 < (box['width'] * box['height']) < 25000 and len(txt) < 50:
                                    await el.click()
                                    clicked_dropdown = True
                                    log_callback(f"[Task {task_id}] Đã bấm mở menu chọn Model ('{txt}').")
                                    await asyncio.sleep(1.5)
                                    break
                        except: pass
                        
                    if clicked_dropdown:
                        opt = page.get_by_text(next_model, exact=False).first
                        if await opt.is_visible():
                            await opt.click()
                            log_callback(f"[Task {task_id}] ✅ Đã chuyển sang model '{next_model}' trên giao diện web thành công!")
                            await asyncio.sleep(2)
                            return True
                        else:
                            menu_items = await page.locator('div[role="menuitem"], div[role="option"], li, button, span').all()
                            for item in menu_items:
                                txt = await item.inner_text()
                                if next_model.lower() in txt.lower():
                                    await item.click()
                                    log_callback(f"[Task {task_id}] ✅ Đã chọn model '{txt.strip()}'.")
                                    await asyncio.sleep(2)
                                    return True
                except Exception as ex:
                    log_callback(f"[Task {task_id}] Lỗi khi tương tác với menu chọn Model: {ex}")
                    
                return True
        except Exception as e:
            log_callback(f"[Task {task_id}] Lỗi kiểm tra hạn mức: {e}")
        return False

    async def ensure_logged_in_and_in_project(self, page, task_id, log_callback=print, is_running_func=None):
        """Waits gracefully until page is inside a Google Flow project studio."""
        import asyncio, time
        last_log = 0
        while True:
            if is_running_func and not is_running_func():
                log_callback(f"[Task {task_id}] Tác vụ đã bị dừng bởi người dùng.")
                return False
            try:
                url = page.url
                
                # If on Google Sign In / Accounts page
                if "accounts.google.com" in url or "signin" in url:
                    now = time.time()
                    if now - last_log > 10:
                        log_callback(f"[Task {task_id}] 🔑 Đang chờ bạn Đăng nhập Google trên cửa sổ Chrome... (Bot sẽ tự chạy tiếp ngay khi đăng nhập xong)")
                        last_log = now
                    await asyncio.sleep(2)
                    continue
                    
                # If inside project studio
                if "project" in url:
                    return True
                    
                textboxes = await page.get_by_role("textbox").all()
                if textboxes and await textboxes[-1].is_visible():
                    return True

                # On Landing Page, click "Dự án mới" / "New project" or existing project card
                clicked = False
                
                # 1. Thử click nút "+ Dự án mới"
                try:
                    new_proj_loc = page.locator('div, span, button, a').filter(has_text="Dự án mới").or_(
                        page.locator('div, span, button, a').filter(has_text="New project")
                    )
                    count = await new_proj_loc.count()
                    for i in reversed(range(count)):
                        el = new_proj_loc.nth(i)
                        if await el.is_visible():
                            await el.click(timeout=3000)
                            log_callback(f"[Task {task_id}] 🎯 Đã bấm '+ Dự án mới'. Đang vào phòng studio...")
                            clicked = True
                            await asyncio.sleep(3)
                            break
                except Exception:
                    pass

                # 2. Thử click thumbnail dự án có sẵn
                if not clicked:
                    try:
                        project_cards = await page.locator('a[href*="project"], div[role="button"]').all()
                        for card in project_cards:
                            if await card.is_visible():
                                await card.click(timeout=3000)
                                log_callback(f"[Task {task_id}] 🎯 Đã bấm mở Dự án để vào Studio...")
                                clicked = True
                                await asyncio.sleep(3)
                                break
                    except Exception:
                        pass
                        
                if not clicked:
                    now = time.time()
                    if now - last_log > 8:
                        log_callback(f"[Task {task_id}] ⏸️ Đang tự động bấm 'Dự án mới' để vào giao diện tạo ảnh...")
                        last_log = now
                    await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(2)

    async def process_task(self, task_id, prompt, image_path, output_dir, log_callback=print, is_running_func=None):
        import os
        import time

        if getattr(self, 'available_pages', None) is None:
            self.available_pages = []
        if getattr(self, 'in_use_pages', None) is None:
            self.in_use_pages = set()
        if getattr(self, 'page_lock', None) is None:
            self.page_lock = asyncio.Lock()

        context = self.browser.contexts[0] if (self.browser and hasattr(self.browser, 'contexts') and self.browser.contexts) else None
        
        # Đảm bảo mỗi Worker giữ riêng 1 tab độc lập (Đa luồng song song)
        async with self.page_lock:
            page = None
            while self.available_pages:
                p = self.available_pages.pop()
                if p and not p.is_closed() and p not in self.in_use_pages:
                    page = p
                    break

            if page is None and context and context.pages:
                for p in context.pages:
                    if p and not p.is_closed() and p not in self.in_use_pages:
                        page = p
                        break

            target_url = getattr(self, 'current_project_url', None) or "https://labs.google/fx/vi/tools/flow"

            if page is None or page.is_closed():
                if context:
                    page = await context.new_page()
                    log_callback(f"[Task {task_id}] 🚀 Mở tab song song trên Chrome...")
                    await page.goto(target_url, timeout=30000)
                elif hasattr(self.browser, 'new_page'):
                    page = await self.browser.new_page()
                    log_callback(f"[Task {task_id}] 🚀 Mở tab song song trên Chrome...")
                    await page.goto(target_url, timeout=30000)
            else:
                log_callback(f"[Task {task_id}] ⚡ Tái sử dụng tab rảnh trong luồng...")
                try:
                    clear_buttons = await page.locator('button:has-text("Xoá câu lệnh"), button:has-text("Clear prompt"), button[aria-label*="Xoá"], button[aria-label*="Clear"]').all()
                    cleared = False
                    for btn in clear_buttons:
                        if await btn.is_visible():
                            await btn.click()
                            cleared = True
                            break
                    
                    if not cleared:
                        textboxes = await page.get_by_role("textbox").all()
                        if textboxes:
                            await textboxes[-1].fill("")
                except Exception:
                    pass

            if page:
                self.in_use_pages.add(page)
            
        try:
            # Gracefully ensure logged in and inside project studio before inputting prompt
            logged_in = await self.ensure_logged_in_and_in_project(page, task_id, log_callback, is_running_func)
            if not logged_in:
                return False, "Task cancelled or not logged in"
            
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except Exception:
                pass
            
            # Pre-check for limit error before inputting prompt
            switched = await self.check_and_switch_model_if_limit_reached(page, task_id, log_callback)
            if switched:
                return False, f"Quota limit reached. Auto switched model to {self.model}"
            
            # 1. UPLOAD REFERENCE IMAGE FIRST
            last_uploaded = getattr(page, 'last_uploaded_image', None)
            if image_path and os.path.exists(image_path) and last_uploaded != image_path:
                log_callback(f"[Task {task_id}] Uploading reference image: {image_path}")
                try:
                    await page.get_by_text("Thêm nội dung nghe nhìn").click(timeout=5000)
                    await asyncio.sleep(2)
                    
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await page.get_by_text("Tải nội dung nghe nhìn lên").click(timeout=5000)
                        
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(image_path)
                    
                    log_callback(f"[Task {task_id}] Waiting 12 seconds for image to fully upload...")
                    await asyncio.sleep(12) # Long wait to ensure upload finishes
                    page.last_uploaded_image = image_path
                except Exception as e:
                    log_callback(f"[Task {task_id}] Error uploading reference image: {str(e)}")
            
            # 2. INPUT PROMPT (PASTE HOẶC TYPE)
            # 2. INPUT PROMPT (DÁN TỨC THÌ SIÊU TỐC)
            log_callback(f"[Task {task_id}] ⚡ Đang dán prompt tức thì...")
            textboxes = None
            for _ in range(5):
                textboxes = await page.get_by_role("textbox").all()
                if textboxes:
                    break
                await asyncio.sleep(1)
                
            if textboxes:
                prompt_input = textboxes[-1]
                await prompt_input.click()
                await asyncio.sleep(0.1)
                
                # Xóa sạch bất kỳ ký tự cũ nào trong hộp thoại
                await page.keyboard.press("Meta+A")
                await page.keyboard.press("Backspace")
                
                # Dán tức thì toàn bộ chuỗi prompt trong 0.01 giây (Không gõ từng phím)
                await page.keyboard.insert_text(prompt)
            else:
                log_callback(f"[Task {task_id}] Error: Could not find prompt input.")
                return False, "Could not find prompt input"
                
            await asyncio.sleep(0.5)
            
            # 3. SET MODEL ON PAGE TO MATCH USER SELECTION
            await self.select_model_on_page(page, self.model, task_id, log_callback)
            
            # 4. RECORD EXISTING IMAGES
            existing_image_srcs = set()
            for img in await page.locator("img").all():
                try:
                    src = await img.get_attribute("src")
                    if src: existing_image_srcs.add(src)
                except: pass
            
            # 5. CLICK GENERATE
            log_callback(f"[Task {task_id}] Clicking Generate (Model: {self.model})...")
            buttons = await page.get_by_role("button").all()
            clicked = False
            for btn in buttons:
                text = await btn.inner_text()
                if text and "arrow_forward" in text:
                    await btn.click()
                    clicked = True
                    break
            
            if not clicked:
                log_callback(f"[Task {task_id}] Error: Could not find Generate button.")
                return False, "Could not find Generate button"
            
            log_callback(f"[Task {task_id}] Waiting for generation to complete...")
            
            # 6. WAIT FOR NEW LARGE IMAGE
            success = False
            img_element = None
            
            for i in range(45): # 90 seconds timeout
                if is_running_func and not is_running_func():
                    log_callback(f"[Task {task_id}] Tác vụ đã dừng.")
                    return False, "Stopped by user"
                await asyncio.sleep(2)
                
                new_images = []
                images = await page.locator("img").all()
                for img in images:
                    try:
                        src = await img.get_attribute("src")
                        if src and src not in existing_image_srcs:
                            box = await img.bounding_box()
                            if box and box['width'] > 150 and box['height'] > 150:
                                new_images.append(img)
                    except: pass
                
                if new_images:
                    success = True
                    break
            
            # 7. SAVE IMAGE
            if success and new_images:
                log_callback(f"[Task {task_id}] Found {len(new_images)} generated images! Downloading original images...")
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    import base64
                    
                    await asyncio.sleep(2) 
                    
                    saved_paths = []
                    for idx, img_el in enumerate(new_images):
                        if idx == 0:
                            filename = f"{task_id}.png"
                        else:
                            filename = f"{task_id}_{idx+1}.png"
                            
                        output_path = os.path.join(output_dir, filename)
                        
                        data_url = await page.evaluate('''
                            (img) => {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth || img.width;
                                canvas.height = img.naturalHeight || img.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                return canvas.toDataURL('image/png');
                            }
                        ''', await img_el.element_handle())
                        
                        if data_url and ',' in data_url:
                            header, data = data_url.split(',', 1)
                            img_bytes = base64.b64decode(data)
                            with open(output_path, "wb") as f:
                                f.write(img_bytes)
                                
                            saved_paths.append(output_path)
                            
                    log_callback(f"[Task {task_id}] Successfully saved {len(saved_paths)} images.")
                    return True, saved_paths[0] if saved_paths else None
                        
                except Exception as e:
                    log_callback(f"[Task {task_id}] Error saving images: {str(e)}")
                    return False, f"Error saving images: {str(e)}"
            else:
                switched = await self.check_and_switch_model_if_limit_reached(page, task_id, log_callback)
                if switched:
                    return False, f"Quota limit reached. Auto switched model to {self.model}"
                log_callback(f"[Task {task_id}] Timeout waiting for image to generate.")
                return False, "Timeout"
            
        except Exception as e:
            if is_running_func and not is_running_func():
                log_callback(f"[Task {task_id}] Tác vụ đã dừng.")
                return False, "Stopped by user"
            log_callback(f"[Task {task_id}] Unexpected error: {str(e)}")
            return False, f"Unexpected error: {str(e)}"
        finally:
            if getattr(self, 'in_use_pages', None) and page in self.in_use_pages:
                self.in_use_pages.remove(page)
                
            if is_running_func and not is_running_func():
                try:
                    if page and not page.is_closed():
                        await page.close()
                except Exception:
                    pass
            elif page and not page.is_closed():
                self.available_pages.append(page)
            log_callback(f"[Task {task_id}] Finished processing prompt.")
