import os
import shutil
import tempfile
import time
import atexit
import traceback
import json
from threading import Thread, Lock
import customtkinter as ctk

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementNotInteractableException

# Chrome Imports
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

# Firefox Imports
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions

# ============================================================
# CONFIG & GLOBALS
# ============================================================
REAL_CHROME_PROFILE = (
    "/path/to/chrome/profile"
)
REAL_FIREFOX_PROFILE = (
    "/path/to/firefox/profile"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GECKODRIVER_PATH = os.path.join(BASE_DIR, "webdrivers", "geckodriver")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

def load_config():
    defaults = {
        "headless": False,
        "browser": "Chrome",
        "ai_states": {
            "chatgpt": True,
            "gemini": True,
            "grok": True,
            "claude": True
        }
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(defaults, f, indent=4)
        return defaults
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return defaults

config_data = load_config()
TEMP_ROOT = tempfile.mkdtemp(prefix="llmx_")

chatgpt_driver = None
gemini_driver = None
grok_driver = None
claude_driver = None
drivers_started = False

driver_locks = {
    "chatgpt": Lock(),
    "gemini": Lock(),
    "grok": Lock(),
    "claude": Lock()
}

responses_store = {
    "chatgpt": "",
    "gemini": "",
    "grok": "",
    "claude": ""
}

spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
spinner_index = 0

ai_status = {
    "chatgpt": "Idle",
    "gemini": "Idle",
    "grok": "Idle",
    "claude": "Idle"
}
ai_generating = {
    "chatgpt": False,
    "gemini": False,
    "grok": False,
    "claude": False
}

def save_config(*args):
    try:
        current_config = {
            "headless": headless_var.get(),
            "browser": browser_var.get(),
            "ai_states": {
                "chatgpt": ai_enabled_vars["chatgpt"].get(),
                "gemini": ai_enabled_vars["gemini"].get(),
                "grok": ai_enabled_vars["grok"].get(),
                "claude": ai_enabled_vars["claude"].get()
            }
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(current_config, f, indent=4)
    except:
        pass

# ============================================================
# CLEANUP
# ============================================================
def cleanup():
    try:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)
    except:
        pass
atexit.register(cleanup)

# ============================================================
# IGNORE FILES (Unified for Chrome & Firefox)
# ============================================================
def ignore_files(directory, files):
    ignored = []
    bad = [
        "SingletonLock", "SingletonCookie", "SingletonSocket", "LOCK", ".lock",
        "lock", "parent.lock", ".parentlock", "sessionstore.jsonlz4", "sessionstore-backups",
        "singletonLock", "singletonCookie", "singletonSocket"
    ]
    for file in files:
        if file in bad:
            ignored.append(file)
    return ignored

# ============================================================
# CLONE PROFILE
# ============================================================
def clone_profile(name, browser_type):
    dst = os.path.join(TEMP_ROOT, name)
    src = REAL_CHROME_PROFILE if browser_type == "Chrome" else REAL_FIREFOX_PROFILE
    
    shutil.copytree(
        src,
        dst,
        ignore=ignore_files,
        dirs_exist_ok=True
    )
    return dst

# ============================================================
# CREATE CHROME DRIVER (UNTOUCHED)
# ============================================================
def create_chrome_driver(name, headless=False):
    profile_path = clone_profile(name, "Chrome")
    options = ChromeOptions()
    
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--password-store=basic")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-infobars")
    
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1700,1200")
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })
    except:
        pass
        
    return driver

# ============================================================
# CREATE FIREFOX DRIVER
# ============================================================
def create_firefox_driver(name, headless=False):
    if not os.path.exists(GECKODRIVER_PATH):
        raise Exception(f"GeckoDriver missing:\n{GECKODRIVER_PATH}")

    profile_path = clone_profile(name, "Firefox")
    options = FirefoxOptions()
    
    options.binary_location = "/usr/bin/firefox"
    options.add_argument("-profile")
    options.add_argument(profile_path)
    
    if headless:
        options.add_argument("--headless")
        
    options.add_argument("--width=1700")
    options.add_argument("--height=1200")
    
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    service = FirefoxService(executable_path=GECKODRIVER_PATH)
    driver = webdriver.Firefox(service=service, options=options)
    
    try:
        driver.execute_script("""
            Object.defineProperty(
                navigator,
                'webdriver',
                {
                    get: () => undefined
                }
            );
        """)
    except:
        pass
        
    return driver

# ============================================================
# THREAD SAFE UI
# ============================================================
def ui_update(widget, text):
    root.after(
        0,
        lambda: (
            widget.delete("1.0", "end"),
            widget.insert("end", text)
        )
    )

# ============================================================
# COPY & DOWNLOAD
# ============================================================
def copy_response(key):
    try:
        root.clipboard_clear()
        root.clipboard_append(responses_store[key])
    except:
        pass

def download_response(key):
    try:
        content = responses_store.get(key, "")
        if not content:
            return
        filepath = ctk.filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"{key}_response.txt",
            title=f"Save {key.upper()} Response",
            filetypes=[("Text Files", "*.txt"), ("Markdown Files", "*.md"), ("All Files", "*.*")]
        )
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception as e:
        print(f"Download Error: {e}")

def download_html(key):
    try:
        driver = None
        if key == "chatgpt": driver = chatgpt_driver
        elif key == "gemini": driver = gemini_driver
        elif key == "grok": driver = grok_driver
        elif key == "claude": driver = claude_driver
        
        if not driver:
            return
            
        page_source = driver.page_source
        filepath = ctk.filedialog.asksaveasfilename(
            defaultextension=".html",
            initialfile=f"{key}_full_page.html",
            title=f"Save {key.upper()} Full HTML Page",
            filetypes=[("HTML Files", "*.html"), ("All Files", "*.*")]
        )
        
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(page_source)
    except Exception as e:
        print(f"HTML Download Error: {e}")

# ============================================================
# CLEAR PROMPT
# ============================================================
def clear_prompt():
    query_entry.delete(0, "end")

# ============================================================
# SPINNER LOOP
# ============================================================
def spinner_loop():
    global spinner_index
    frame = spinner_frames[spinner_index % len(spinner_frames)]
    spinner_index += 1
    
    # CHATGPT STATUS
    if not ai_enabled_vars["chatgpt"].get():
        chatgpt_status.configure(text="OFF")
    elif ai_generating["chatgpt"]:
        chatgpt_status.configure(text=f"{frame} {ai_status['chatgpt']}")
    else:
        chatgpt_status.configure(text=ai_status["chatgpt"])
        
    # GEMINI STATUS
    if not ai_enabled_vars["gemini"].get():
        gemini_status.configure(text="OFF")
    elif ai_generating["gemini"]:
        gemini_status.configure(text=f"{frame} {ai_status['gemini']}")
    else:
        gemini_status.configure(text=ai_status["gemini"])
        
    # GROK STATUS
    if not ai_enabled_vars["grok"].get():
        grok_status.configure(text="OFF")
    elif ai_generating["grok"]:
        grok_status.configure(text=f"{frame} {ai_status['grok']}")
    else:
        grok_status.configure(text=ai_status["grok"])
        
    # CLAUDE STATUS
    if not ai_enabled_vars["claude"].get():
        claude_status.configure(text="OFF")
    elif ai_generating["claude"]:
        claude_status.configure(text=f"{frame} {ai_status['claude']}")
    else:
        claude_status.configure(text=ai_status["claude"])
        
    root.after(120, spinner_loop)

# ============================================================
# REINFORCED TRANSMISSION & RESPONSE POLLING ENGINE
# ============================================================
def robust_transmit_prompt(driver, textarea, prompt, fallback_send_selector=None):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", textarea)
        time.sleep(0.1)
        textarea.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].focus();", textarea)
        except:
            pass
            
    time.sleep(0.2)
    
    try:
        textarea.send_keys(Keys.CONTROL + "a")
        textarea.send_keys(Keys.BACKSPACE)
    except:
        pass
        
    time.sleep(0.2)
    
    try:
        textarea.send_keys(prompt)
    except ElementNotInteractableException:
        driver.execute_script("arguments[0].value = arguments[1];", textarea, prompt)
        
    time.sleep(0.3)
    
    try:
        textarea.send_keys(Keys.ENTER)
    except:
        pass
    
    transmitted = False
    for _ in range(8):
        try:
            current_input = textarea.text or textarea.get_attribute("value") or ""
            if not current_input.strip():
                transmitted = True
                break
        except:
            pass
        time.sleep(0.2)
        
    if not transmitted and fallback_send_selector:
        try:
            send_buttons = driver.find_elements(By.CSS_SELECTOR, fallback_send_selector)
            for btn in send_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    try:
                        driver.execute_script("arguments[0].click();", btn)
                    except:
                        btn.click()
                    transmitted = True
                    break
        except:
            pass
            
    time.sleep(0.5)

def poll_response(extractor, driver, stop_selectors=[], callback=None, old_text="", timeout=300):
    start_time = time.time()
    latest_content = ""
    stable_ticks = 0
    required_ticks = 4 
    generation_started = False
    
    for _ in range(30): 
        if (time.time() - start_time) > timeout:
            break
        try:
            initial_text = extractor()
            if initial_text and initial_text.strip() != old_text.strip():
                generation_started = True
                break
        except:
            pass
        time.sleep(0.5)
        
    if not generation_started:
        try:
            final_snapshot = extractor()
            if final_snapshot:
                return final_snapshot
        except:
            pass
            
    while (time.time() - start_time) < timeout:
        try:
            current_text = extractor()
            
            if current_text:
                if current_text != latest_content:
                    latest_content = current_text
                    stable_ticks = 0
                    if callback:
                        callback(latest_content)
                else:
                    stable_ticks += 1
                    
                active_generation_detected = False
                if stop_selectors and driver:
                    for selector in stop_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            if elements and any(el.is_displayed() for el in elements):
                                active_generation_detected = True
                                break
                        except:
                            pass
                
                if stop_selectors and not active_generation_detected and stable_ticks >= 2:
                    time.sleep(0.5)
                    if extractor() == latest_content:
                        return latest_content
                        
                if stable_ticks >= required_ticks:
                    time.sleep(1.0)
                    if extractor() == latest_content:
                        return latest_content
        except:
            pass
        time.sleep(1.0)
    return latest_content

# ============================================================
# CHATGPT
# ============================================================
def chatgpt_latest():
    try:
        responses = chatgpt_driver.find_elements(By.CSS_SELECTOR, "div.markdown")
        texts = [r.text.strip() for r in responses if r.text.strip()]
        if texts:
            return texts[-1]
    except:
        pass
    return ""

def ask_chatgpt(prompt):
    try:
        ai_generating["chatgpt"] = True
        ai_status["chatgpt"] = "Entering prompt..."
        wait = WebDriverWait(chatgpt_driver, 240)
        textarea = wait.until(
            lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"]') if el.is_displayed() and el.is_enabled()), False)
        )
        old = chatgpt_latest()
        robust_transmit_prompt(
            chatgpt_driver, 
            textarea, 
            prompt, 
            fallback_send_selector='button[data-testid="send-button"]'
        )
        ai_status["chatgpt"] = "Generating..."
        result = poll_response(
            chatgpt_latest,
            chatgpt_driver,
            stop_selectors=['button[data-testid="stop-button"]', 'div.streaming'],
            callback=lambda txt: ui_update(chatgpt_box, txt),
            old_text=old
        )
        ai_status["chatgpt"] = "Done"
        ai_generating["chatgpt"] = False
        return result
    except Exception as e:
        ai_status["chatgpt"] = "Error"
        ai_generating["chatgpt"] = False
        return f"ChatGPT Error:\n{e}"

# ============================================================
# GEMINI
# ============================================================
def gemini_latest():
    try:
        responses = gemini_driver.find_elements(By.CSS_SELECTOR, "message-content, .markdown, .model-response-text")
        texts = [r.text.strip() for r in responses if r.text.strip()]
        if texts:
            return texts[-1]
    except:
        pass
    return ""

def ask_gemini(prompt):
    try:
        ai_generating["gemini"] = True
        ai_status["gemini"] = "Entering prompt..."
        wait = WebDriverWait(gemini_driver, 240)
        textarea = wait.until(
            lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, "div.ql-editor, div[contenteditable='true'][role='textbox']") if el.is_displayed() and el.is_enabled()), False)
        )
        old = gemini_latest()
        robust_transmit_prompt(
            gemini_driver, 
            textarea, 
            prompt, 
            fallback_send_selector='button[aria-label*="Send"], button[mattooltip*="Send"]'
        )
        ai_status["gemini"] = "Generating..."
        result = poll_response(
            gemini_latest,
            gemini_driver,
            stop_selectors=['button[aria-label="Stop generating"]', 'mat-progress-spinner'],
            callback=lambda txt: ui_update(gemini_box, txt),
            old_text=old
        )
        ai_status["gemini"] = "Done"
        ai_generating["gemini"] = False
        return result
    except Exception as e:
        ai_status["gemini"] = "Error"
        ai_generating["gemini"] = False
        return f"Gemini Error:\n{e}"

# ============================================================
# GROK
# ============================================================
def grok_latest():
    try:
        responses = grok_driver.find_elements(By.CSS_SELECTOR, "div.response-content-markdown")
        texts = [r.text.strip() for r in responses if r.text.strip()]
        if texts:
            return texts[-1]
    except:
        pass
    return ""

def ask_grok(prompt):
    try:
        ai_generating["grok"] = True
        ai_status["grok"] = "Entering prompt..."
        wait = WebDriverWait(grok_driver, 240)
        textarea = wait.until(
            lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div.ProseMirror[contenteditable="true"]') if el.is_displayed() and el.is_enabled()), False)
        )
        old = grok_latest()
        robust_transmit_prompt(
            grok_driver, 
            textarea, 
            prompt, 
            fallback_send_selector='button[aria-label="Grok query"]'
        )
        ai_status["grok"] = "Generating..."
        result = poll_response(
            grok_latest,
            grok_driver,
            stop_selectors=['button[aria-label="Stop"]', '.thinking-container'],
            callback=lambda txt: ui_update(grok_box, txt),
            old_text=old
        )
        ai_status["grok"] = "Done"
        ai_generating["grok"] = False
        return result
    except Exception as e:
        ai_status["grok"] = "Error"
        ai_generating["grok"] = False
        return f"Grok Error:\n{e}"

# ============================================================
# CLAUDE
# ============================================================
def claude_latest():
    selectors = [
        "div.font-claude-response",
        ".font-claude-response-body",
        ".standard-markdown",
        "div.prose",
        "[data-testid='message-text']",
        ".font-claude-message"
    ]
    for selector in selectors:
        try:
            responses = claude_driver.find_elements(By.CSS_SELECTOR, selector)
            texts = [r.text.strip() for r in responses if r.text.strip()]
            if texts:
                return texts[-1]
        except Exception:
            continue
    return ""

def ask_claude(prompt):
    try:
        ai_generating["claude"] = True
        ai_status["claude"] = "Entering prompt..."
        wait = WebDriverWait(claude_driver, 240)
        textarea = wait.until(
            lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"], fieldset div.ProseMirror') if el.is_displayed() and el.is_enabled()), False)
        )
        old = claude_latest()
        robust_transmit_prompt(
            claude_driver, 
            textarea, 
            prompt, 
            fallback_send_selector='button[aria-label="Send Message"], button[data-testid="send-button"]'
        )
        ai_status["claude"] = "Generating..."
        result = poll_response(
            claude_latest,
            claude_driver,
            stop_selectors=['button[aria-label="Stop Response"]', 'svg.animate-spin'],
            callback=lambda txt: ui_update(claude_box, txt),
            old_text=old
        )
        ai_status["claude"] = "Done"
        ai_generating["claude"] = False
        return result
    except Exception as e:
        ai_status["claude"] = "Error"
        ai_generating["claude"] = False
        return f"Claude Error:\n{e}"

# ============================================================
# SELECTIVE BROWSER STARTER
# ============================================================
def ensure_driver_for_key(key):
    global chatgpt_driver, gemini_driver, grok_driver, claude_driver
    
    headless = headless_var.get()
    selected_browser = browser_var.get()
    
    root.after(0, lambda: headless_switch.configure(state="disabled"))
    root.after(0, lambda: browser_switch.configure(state="disabled"))
    
    with driver_locks[key]:
        # Choose the correct driver factory based on the selected browser
        driver_factory = create_chrome_driver if selected_browser == "Chrome" else create_firefox_driver

        if key == "chatgpt" and chatgpt_driver is None:
            ai_status["chatgpt"] = f"Opening {selected_browser}..."
            chatgpt_driver = driver_factory("chatgpt", headless=headless)
            chatgpt_driver.get("https://chatgpt.com/?temporary-chat=true")
            try:
                WebDriverWait(chatgpt_driver, 15).until(
                    lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"]') if el.is_displayed() and el.is_enabled()), False)
                )
            except:
                chatgpt_driver.refresh()
            ai_status["chatgpt"] = "Ready"
            
        elif key == "gemini" and gemini_driver is None:
            ai_status["gemini"] = f"Opening {selected_browser}..."
            gemini_driver = driver_factory("gemini", headless=headless)
            gemini_driver.get("https://gemini.google.com/app?pli=1") 
            try:
                WebDriverWait(gemini_driver, 10).until(
                    lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, "div.ql-editor, div[contenteditable='true'][role='textbox']") if el.is_displayed() and el.is_enabled()), False)
                )
            except:
                gemini_driver.refresh()
                try:
                    WebDriverWait(gemini_driver, 15).until(
                        lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, "div.ql-editor, div[contenteditable='true'][role='textbox']") if el.is_displayed() and el.is_enabled()), False)
                    )
                except:
                    pass
            ai_status["gemini"] = "Ready"
            
        elif key == "grok" and grok_driver is None:
            ai_status["grok"] = f"Opening {selected_browser}..."
            grok_driver = driver_factory("grok", headless=headless)
            grok_driver.get("https://grok.com/c#private")
            try:
                WebDriverWait(grok_driver, 15).until(
                    lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div.ProseMirror[contenteditable="true"]') if el.is_displayed() and el.is_enabled()), False)
                )
            except:
                grok_driver.refresh()
            ai_status["grok"] = "Ready"
            
        elif key == "claude" and claude_driver is None:
            ai_status["claude"] = f"Opening {selected_browser}..."
            claude_driver = driver_factory("claude", headless=headless)
            claude_driver.get("https://claude.ai/new?incognito=")
            try:
                WebDriverWait(claude_driver, 15).until(
                    lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"], fieldset div.ProseMirror') if el.is_displayed() and el.is_enabled()), False)
                )
            except:
                claude_driver.refresh()
            ai_status["claude"] = "Ready"

def start_browsers():
    global drivers_started
    if drivers_started:
        return
    if ai_enabled_vars["chatgpt"].get():
        Thread(target=ensure_driver_for_key, args=("chatgpt",), daemon=True).start()
    if ai_enabled_vars["gemini"].get():
        Thread(target=ensure_driver_for_key, args=("gemini",), daemon=True).start()
    if ai_enabled_vars["grok"].get():
        Thread(target=ensure_driver_for_key, args=("grok",), daemon=True).start()
    if ai_enabled_vars["claude"].get():
        Thread(target=ensure_driver_for_key, args=("claude",), daemon=True).start()
    drivers_started = True

# ============================================================
# GUI SETUP
# ============================================================
ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.title("LLMX")
root.geometry("1920x1040")
root.configure(fg_color="#020202")

ai_enabled_vars = {
    "chatgpt": ctk.BooleanVar(value=config_data.get("ai_states", {}).get("chatgpt", True)),
    "gemini": ctk.BooleanVar(value=config_data.get("ai_states", {}).get("gemini", True)),
    "grok": ctk.BooleanVar(value=config_data.get("ai_states", {}).get("grok", True)),
    "claude": ctk.BooleanVar(value=config_data.get("ai_states", {}).get("claude", True))
}

# ============================================================
# HEADER
# ============================================================
header = ctk.CTkLabel(
    root,
    text="LLMX",
    font=("Orbitron", 34, "bold"),
    text_color="#00FFFF"
)
header.pack(pady=(12, 8))

# ============================================================
# INPUT FRAME Layout: headless switch | Browser switch | searchbox | X | Send
# ============================================================
input_frame = ctk.CTkFrame(
    root,
    fg_color="#050505",
    border_color="#00FFFF",
    border_width=2,
    corner_radius=18
)
input_frame.pack(fill="x", padx=20, pady=10)

headless_var = ctk.BooleanVar(value=config_data.get("headless", False))
headless_switch = ctk.CTkSwitch(
    input_frame,
    text="Headless",
    variable=headless_var,
    width=80,
    progress_color="#00FFFF",
    button_color="#00FFFF",
    button_hover_color="#00AAAA",
    command=save_config
)
headless_switch.pack(side="left", padx=(12, 6), pady=12)

# --- BROWSER SELECTOR ---
browser_var = ctk.StringVar(value=config_data.get("browser", "Chrome"))
browser_switch = ctk.CTkSegmentedButton(
    input_frame,
    values=["Chrome", "Firefox"],
    variable=browser_var,
    command=save_config,
    selected_color="#00AAAA",
    selected_hover_color="#00FFFF"
)
browser_switch.pack(side="left", padx=(6, 6), pady=12)

query_entry = ctk.CTkEntry(
    input_frame,
    height=55,
    font=("Consolas", 16),
    text_color="#00FFFF",
    fg_color="#000000",
    border_color="#00FFFF",
    corner_radius=12
)
query_entry.pack(side="left", fill="x", expand=True, padx=(6, 6), pady=12)

clear_btn = ctk.CTkButton(
    input_frame,
    text="✕",
    width=42,
    height=42,
    font=("Arial", 18, "bold"),
    fg_color="#111111",
    hover_color="#FF4444",
    text_color="#FFFFFF",
    command=clear_prompt
)
clear_btn.pack(side="left", padx=(0, 6))

send_button = ctk.CTkButton(
    input_frame,
    text="SEND",
    width=120,
    height=55,
    font=("Orbitron", 15, "bold"),
    fg_color="#00AAAA",
    hover_color="#00FFFF",
    text_color="#000000",
    corner_radius=12
)
send_button.pack(side="right", padx=12, pady=12)

# ============================================================
# PROCESS SINGLE QUERY (FOLLOW-UP)
# ============================================================
def process_single_query(key, prompt):
    global drivers_started
    if not ai_enabled_vars[key].get():
        return
    ensure_driver_for_key(key)
    drivers_started = True
    
    if key == "chatgpt":
        ui_update(chatgpt_box, "Generating...")
        resp = ask_chatgpt(prompt)
        responses_store["chatgpt"] = resp
        ui_update(chatgpt_box, resp)
    elif key == "gemini":
        ui_update(gemini_box, "Generating...")
        resp = ask_gemini(prompt)
        responses_store["gemini"] = resp
        ui_update(gemini_box, resp)
    elif key == "grok":
        ui_update(grok_box, "Generating...")
        resp = ask_grok(prompt)
        responses_store["grok"] = resp
        ui_update(grok_box, resp)
    elif key == "claude":
        ui_update(claude_box, "Generating...")
        resp = ask_claude(prompt)
        responses_store["claude"] = resp
        ui_update(claude_box, resp)

# ============================================================
# SCROLLABLE PANEL FRAME (HORIZONTAL SCROLLING)
# ============================================================
panel_frame = ctk.CTkScrollableFrame(
    root,
    fg_color="#020202",
    orientation="horizontal"
)
panel_frame.pack(fill="both", expand=True, padx=20, pady=10)

# ============================================================
# CREATE PANEL
# ============================================================
def create_panel(title, key):
    frame = ctk.CTkFrame(
        panel_frame,
        width=460,
        height=700,
        fg_color="#050505",
        border_color="#00FFFF",
        border_width=2,
        corner_radius=18
    )
    frame.pack(side="left", fill="both", expand=True, padx=8, pady=8)
    frame.pack_propagate(False)
    
    top = ctk.CTkFrame(frame, fg_color="transparent")
    top.pack(fill="x", padx=10, pady=(10, 0))
    
    label = ctk.CTkLabel(
        top,
        text=title,
        font=("Orbitron", 20, "bold"),
        text_color="#00FFFF"
    )
    label.pack(side="left")
    
    status = ctk.CTkLabel(
        top,
        text="Idle",
        font=("Consolas", 12),
        text_color="#00FFFF"
    )
    status.pack(side="left", padx=12)
    
    copy_btn = ctk.CTkButton(
        top,
        text="📋",
        width=36,
        height=30,
        fg_color="#00AAAA",
        hover_color="#00FFFF",
        text_color="#000000",
        command=lambda: copy_response(key)
    )
    copy_btn.pack(side="right")
    
    download_btn = ctk.CTkButton(
        top,
        text="💾",
        width=36,
        height=30,
        fg_color="#00AAAA",
        hover_color="#00FFFF",
        text_color="#000000",
        command=lambda: download_response(key)
    )
    download_btn.pack(side="right", padx=(0, 8))
    
    download_html_btn = ctk.CTkButton(
        top,
        text="🌐",
        width=36,
        height=30,
        fg_color="#00AAAA",
        hover_color="#00FFFF",
        text_color="#000000",
        command=lambda: download_html(key)
    )
    download_html_btn.pack(side="right", padx=(0, 8))
    
    ai_switch = ctk.CTkSwitch(
        top,
        text="",
        variable=ai_enabled_vars[key],
        width=45,
        progress_color="#00FFFF",
        button_color="#00FFFF",
        button_hover_color="#00AAAA",
        command=save_config
    )
    ai_switch.pack(side="right", padx=(0, 8))
    
    textbox = ctk.CTkTextbox(
        frame,
        font=("Consolas", 14),
        text_color="#00FFFF",
        fg_color="#000000",
        border_color="#00FFFF",
        border_width=1,
        wrap="word",
        corner_radius=12
    )
    textbox.pack(fill="both", expand=True, padx=10, pady=(10, 5))
    
    # --- INDIVIDUAL FOLLOW UP BAR ---
    followup_frame = ctk.CTkFrame(frame, fg_color="transparent")
    followup_frame.pack(fill="x", padx=10, pady=(0, 10))
    followup_entry = ctk.CTkEntry(
        followup_frame,
        placeholder_text=f"Follow up with {title}...",
        font=("Consolas", 14),
        text_color="#00FFFF",
        fg_color="#000000",
        border_color="#00FFFF",
        height=40,
        corner_radius=8
    )
    followup_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    
    def on_followup_send(k=key, entry=followup_entry):
        txt = entry.get().strip()
        if not txt: return
        entry.delete(0, "end")
        Thread(target=process_single_query, args=(k, txt), daemon=True).start()
        
    followup_btn = ctk.CTkButton(
        followup_frame,
        text="➤",
        width=40,
        height=40,
        font=("Arial", 16, "bold"),
        fg_color="#00AAAA",
        hover_color="#00FFFF",
        text_color="#000000",
        command=on_followup_send
    )
    followup_btn.pack(side="right")
    followup_entry.bind("<Return>", lambda e: on_followup_send())
    
    return textbox, status

chatgpt_box, chatgpt_status = create_panel("CHATGPT", "chatgpt")
gemini_box, gemini_status = create_panel("GEMINI", "gemini")
grok_box, grok_status = create_panel("GROK", "grok")
claude_box, claude_status = create_panel("CLAUDE", "claude")

# ============================================================
# PROCESS QUERY (GLOBAL - NOW FULLY PARALLEL)
# ============================================================
def process_query(prompt):
    global drivers_started
    responses_store["chatgpt"] = ""
    responses_store["gemini"] = ""
    responses_store["grok"] = ""
    responses_store["claude"] = ""
    
    if ai_enabled_vars["chatgpt"].get():
        def run_chatgpt():
            ui_update(chatgpt_box, "Initializing browser..." if chatgpt_driver is None else "Generating...")
            ensure_driver_for_key("chatgpt")
            ui_update(chatgpt_box, "Generating...")
            resp = ask_chatgpt(prompt)
            responses_store["chatgpt"] = resp
            ui_update(chatgpt_box, resp)
        Thread(target=run_chatgpt, daemon=True).start()
    else:
        ui_update(chatgpt_box, "[AI Turned OFF]")
        
    if ai_enabled_vars["gemini"].get():
        def run_gemini():
            ui_update(gemini_box, "Initializing browser..." if gemini_driver is None else "Generating...")
            ensure_driver_for_key("gemini")
            ui_update(gemini_box, "Generating...")
            resp = ask_gemini(prompt)
            responses_store["gemini"] = resp
            ui_update(gemini_box, resp)
        Thread(target=run_gemini, daemon=True).start()
    else:
        ui_update(gemini_box, "[AI Turned OFF]")
        
    if ai_enabled_vars["grok"].get():
        def run_grok():
            ui_update(grok_box, "Initializing browser..." if grok_driver is None else "Generating...")
            ensure_driver_for_key("grok")
            ui_update(grok_box, "Generating...")
            resp = ask_grok(prompt)
            responses_store["grok"] = resp
            ui_update(grok_box, resp)
        Thread(target=run_grok, daemon=True).start()
    else:
        ui_update(grok_box, "[AI Turned OFF]")
        
    if ai_enabled_vars["claude"].get():
        def run_claude():
            ui_update(claude_box, "Initializing browser..." if claude_driver is None else "Generating...")
            ensure_driver_for_key("claude")
            ui_update(claude_box, "Generating...")
            resp = ask_claude(prompt)
            responses_store["claude"] = resp
            ui_update(claude_box, resp)
        Thread(target=run_claude, daemon=True).start()
    else:
        ui_update(claude_box, "[AI Turned OFF]")
        
    drivers_started = True

# ============================================================
# SEND ACTION DELEGATION
# ============================================================
def on_send():
    prompt = query_entry.get().strip()
    if not prompt: return
    Thread(target=process_query, args=(prompt,), daemon=True).start()

send_button.configure(command=on_send)
query_entry.bind("<Return>", lambda e: on_send())

# ============================================================
# START SPINNER & MAIN LOOP
# ============================================================
spinner_loop()
root.mainloop()
