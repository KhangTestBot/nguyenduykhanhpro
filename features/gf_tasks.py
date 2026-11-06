import asyncio
import threading
from features.gf_bot import BrowserBot

class TaskManager(threading.Thread):
    def __init__(self, tasks, config, state_dict):
        """
        state_dict is a dictionary to store state so Streamlit can read it.
        It should have:
        - logs: list of strings
        - tasks: list of dicts reflecting current status
        - is_running: bool
        - is_paused: bool
        """
        super().__init__()
        self.tasks = tasks  # list of dicts
        self.config = config
        self.state = state_dict
        self.state['is_running'] = True
        self.state['is_paused'] = False
        self.daemon = True # allow exiting if main thread exits
        self.bot = None
        self.loop = None
        self.async_tasks = []
        
    def log(self, msg):
        import datetime
        now = datetime.datetime.now().strftime('%H:%M:%S')
        self.state['logs'].append(f"{now} - {msg}")
        
    def update_task_status(self, task_id, status_text):
        for t in self.state['tasks']:
            if t['id'] == task_id:
                t['status'] = status_text
                break
                
    def run(self):
        # Create a new event loop for this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.run_async())
        finally:
            try:
                self.loop.close()
            except Exception:
                pass
        
    async def run_async(self):
        port = self.config.get('port', '9222')
        mode = self.config.get('mode', 'Create Image')
        model = self.config.get('model', 'Nano Banana 2')
        ratio = self.config.get('ratio', '16:9')
        input_method = self.config.get('input_method', 'Paste')
        max_tabs = self.config.get('max_tabs', 1)
        output_dir = self.config.get('output_dir', '')
        
        bot = BrowserBot(port, mode, model, ratio, input_method)
        self.bot = bot
        
        def is_running():
            return self.state['is_running']

        connected = await bot.connect(log_callback=self.log)
        if not connected or not is_running():
            if not is_running() and self.bot:
                self.bot.kill_chrome(log_callback=self.log)
            self.state['is_running'] = False
            return

        # Khởi tạo trước tab pool đúng số lượng tabs
        await bot.initialize_tab_pool(max_tabs, log_callback=self.log, is_running_func=is_running)
        if not is_running():
            return
            
        semaphore = asyncio.Semaphore(max_tabs)

        async def worker(task):
            async with semaphore:
                # Check for pause/stop
                while self.state['is_paused'] and self.state['is_running']:
                    await asyncio.sleep(0.5)
                
                if not self.state['is_running']:
                    return
                    
                max_retries = 3
                success = False
                for attempt in range(max_retries):
                    if not self.state['is_running']:
                        break
                        
                    self.update_task_status(task['id'], f"Running (Lần {attempt+1})" if attempt > 0 else "Running")
                    
                    try:
                        success, error = await bot.process_task(
                            task['id'], 
                            task['prompt'], 
                            task.get('image'), 
                            output_dir,
                            log_callback=self.log,
                            is_running_func=is_running
                        )
                    except asyncio.CancelledError:
                        self.update_task_status(task['id'], "Stopped")
                        return
                    except Exception as ex:
                        success = False
                        error = str(ex)
                    
                    if success or not self.state['is_running']:
                        break
                    else:
                        if attempt < max_retries - 1 and self.state['is_running']:
                            self.log(f"[Task {task['id']}] Lỗi: {error}. Đang thử lại lần {attempt+2}/{max_retries}...")
                            await asyncio.sleep(2)
                        
                if not self.state['is_running']:
                    self.update_task_status(task['id'], "Stopped")
                else:
                    self.update_task_status(task['id'], "Success" if success else "Error")

        # Create tasks
        self.async_tasks = [asyncio.create_task(worker(task)) for task in self.tasks]
        try:
            await asyncio.gather(*self.async_tasks, return_exceptions=True)
        except Exception:
            pass
        finally:
            if self.bot:
                await self.bot.disconnect(log_callback=self.log)
            self.state['is_running'] = False
            self.log("All tasks finished or stopped.")
        
    def pause(self):
        self.state['is_paused'] = True
        self.log("Paused tasks.")
        
    def resume(self):
        self.state['is_paused'] = False
        self.log("Resumed tasks.")
        
    def stop(self):
        self.state['is_running'] = False
        self.state['is_paused'] = False
        self.log("⏹ Bấm STOP: Đang dừng tác vụ và KILL toàn bộ tab Chrome...")
        if self.bot:
            try:
                self.bot.kill_chrome(log_callback=self.log)
            except Exception as e:
                self.log(f"Lỗi khi kill Chrome: {e}")
                
        if self.loop and self.loop.is_running():
            for t in self.async_tasks:
                if not t.done():
                    try:
                        self.loop.call_soon_threadsafe(t.cancel)
                    except Exception:
                        pass
