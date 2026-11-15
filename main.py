#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import time
import json
import base64
import random
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# ── Fix lỗi hiển thị Tiếng Việt & Ký tự đặc biệt trên Windows CMD ─────────────
if os.name == "nt":
    os.system("chcp 65001 >nul 2>&1")
    os.system("")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("[ERR] Thiếu thư viện 'requests'. Đang tự động cài đặt...")
    os.system(f'"{sys.executable}" -m pip install requests')
    import requests

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = "https://discord.com/api/v9"
TOKENS_FILE = "tokens.txt"
HEARTBEAT_INTERVAL = 20
AUTO_ACCEPT = True
DEBUG = False

VIDEO_TASKS = [
    "WATCH_VIDEO",
    "WATCH_VIDEO_ON_MOBILE",
]

GAME_TASKS = [
    "PLAY_ON_DESKTOP",
    "PLAY_ON_DESKTOP_V2",
    "STREAM_ON_DESKTOP",
]

# Chỉ hỗ trợ VIDEO và GAME (bỏ qua hoàn toàn Mini-App)
SUPPORTED_TASKS = VIDEO_TASKS + GAME_TASKS


# ── Bảng màu ANSI ──────────────────────────────────────────────────────────────
class Colors:
    RESET   = "\033[0m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"


print_lock = threading.Lock()


def log(msg: str, level: str = "info"):
    if level == "debug" and not DEBUG:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "info":  f"{Colors.CYAN}[INFO]{Colors.RESET}",
        "ok":    f"{Colors.GREEN}[  OK]{Colors.RESET}",
        "warn":  f"{Colors.YELLOW}[WARN]{Colors.RESET}",
        "error": f"{Colors.RED}[ ERR]{Colors.RESET}",
        "debug": f"{Colors.DIM}[DBG ]{Colors.RESET}",
    }.get(level, f"[{level.upper()}]")

    with print_lock:
        print(f"{Colors.DIM}{ts}{Colors.RESET} {prefix} {msg}")


def make_progress_bar(current: float, total: float, width: int = 20, completed: bool = False) -> str:
    if completed:
        bar = "█" * width
        t_val = int(total) if total > 0 else 1
        return f"{Colors.GREEN}[{bar}]{Colors.RESET} 100.0% ({t_val}/{t_val}s)"
    if total <= 0:
        bar = "░" * width
        return f"{Colors.CYAN}[{bar}]{Colors.RESET}   0.0% (0/?s)"
    ratio = min(1.0, max(0.0, current / total))
    filled = int(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    pct = ratio * 100
    return f"{Colors.CYAN}[{bar}]{Colors.RESET} {pct:5.1f}% ({int(current)}/{int(total)}s)"


# ── Lấy Build Number từ Discord ────────────────────────────────────────────────
def fetch_latest_build_number() -> int:
    FALLBACK = 504649
    try:
        log("Đang lấy build number mới nhất từ Discord...", "info")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        r = requests.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=8)
        if r.status_code != 200:
            return FALLBACK

        scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text)
        if not scripts:
            scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
            scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]

        for asset_hash in scripts[-5:]:
            try:
                ar = requests.get(
                    f"https://discord.com/assets/{asset_hash}.js",
                    headers={"User-Agent": ua}, timeout=8
                )
                m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                if m:
                    bn = int(m.group(1))
                    log(f"Build number: {Colors.BOLD}{bn}{Colors.RESET}", "ok")
                    return bn
            except Exception:
                continue
        return FALLBACK
    except Exception:
        return FALLBACK


def make_super_properties(build_number: int) -> str:
    obj = {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": "1.0.9175",
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        ),
        "browser_version": "32.2.7",
        "client_build_number": build_number,
        "native_build_number": 59498,
        "client_event_source": None,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()


# ── Quản lý File Token (tokens.txt) ────────────────────────────────────────────
def clean_token(raw: str) -> str:
    t = raw.strip().strip('"').strip("'").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    if ":" in t and len(t.split(":")) >= 3:
        t = t.split(":")[-1].strip().strip('"').strip("'")
    return t


def load_tokens(filepath: str = TOKENS_FILE) -> List[str]:
    if not os.path.exists(filepath):
        return []
    tokens = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                t = clean_token(line)
                if t and t not in tokens:
                    tokens.append(t)
    except Exception as e:
        log(f"Lỗi đọc file {filepath}: {e}", "error")
    return tokens


def save_tokens(tokens: List[str], filepath: str = TOKENS_FILE):
    unique = []
    for t in tokens:
        ct = clean_token(t)
        if ct and ct not in unique:
            unique.append(ct)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Danh sách Discord Token (Mỗi dòng 1 token)\n")
            for t in unique:
                f.write(f"{t}\n")
        log(f"Đã lưu {len(unique)} token vào file {Colors.BOLD}{filepath}{Colors.RESET}", "ok")
    except Exception as e:
        log(f"Không thể lưu file {filepath}: {e}", "error")


def prompt_add_tokens(filepath: str = TOKENS_FILE) -> List[str]:
    existing = load_tokens(filepath)
    print(f"\n{Colors.BOLD}{Colors.CYAN}── NHẬP DISCORD TOKEN (Lưu vào {filepath}) ──{Colors.RESET}")
    print(f"{Colors.DIM}Nhập từng token.")
    print(f"Nhấn Enter ở dòng trống để hoàn tất nhập.{Colors.RESET}")
    new_count = 0
    while True:
        try:
            raw = input(f"{Colors.BOLD}Token #{len(existing) + 1} (Enter để dừng): {Colors.RESET}").strip()
        except EOFError:
            break
        if not raw:
            break
        parts = [clean_token(p) for p in re.split(r'[,\s]+', raw) if clean_token(p)]
        for p in parts:
            if p not in existing:
                existing.append(p)
                new_count += 1
    if new_count > 0 or not os.path.exists(filepath):
        save_tokens(existing, filepath)
    return existing


# ── Kết nối Discord API ────────────────────────────────────────────────────────
class DiscordAPI:
    def __init__(self, token: str, build_number: int):
        self.token = clean_token(token)
        self.build_number = build_number
        self.user_id = "?"
        self.username = "?"
        self.global_name = "?"
        self.session = requests.Session()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        )
        sp = make_super_properties(build_number)
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": ua,
            "X-Super-Properties": sp,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
        })

    def get(self, path: str, timeout: int = 10, **kwargs) -> requests.Response:
        return self.session.get(f"{API_BASE}{path}", timeout=timeout, **kwargs)

    def post(self, path: str, payload: Optional[dict] = None, timeout: int = 10, **kwargs) -> requests.Response:
        return self.session.post(f"{API_BASE}{path}", json=payload, timeout=timeout, **kwargs)

    def validate_token(self) -> bool:
        try:
            r = self.get("/users/@me")
            if r.status_code == 200:
                user = r.json()
                self.user_id = str(user.get("id", "?"))
                self.username = str(user.get("username", "?"))
                self.global_name = str(user.get("global_name") or self.username)
                return True
            return False
        except Exception:
            return False


# ── Hàm Xử lý Dữ liệu Nhiệm vụ ─────────────────────────────────────────────────
def _get(d: Any, *keys) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str or not isinstance(dt_str, str):
        return None
    try:
        clean = dt_str.strip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_task_config(quest: dict) -> dict:
    cfg = quest.get("config") or {}
    tc = _get(
        cfg,
        "taskConfigV2", "task_config_v2",
        "taskConfigV3", "task_config_v3",
        "taskConfig", "task_config"
    )
    return tc if isinstance(tc, dict) else {}


def get_tasks_dict(quest: dict) -> Dict[str, dict]:
    tc = get_task_config(quest)
    raw_tasks = tc.get("tasks")
    if isinstance(raw_tasks, dict) and raw_tasks:
        return raw_tasks
    if isinstance(raw_tasks, list) and raw_tasks:
        out = {}
        for item in raw_tasks:
            if isinstance(item, dict):
                t_type = item.get("type") or item.get("event_name") or item.get("eventName")
                if t_type:
                    out[str(t_type)] = item
        if out:
            return out

    cfg = quest.get("config") or {}
    for k, v in cfg.items():
        if isinstance(v, dict) and "tasks" in v and isinstance(v["tasks"], dict):
            return v["tasks"]
    return {}


def get_quest_name(quest: dict) -> str:
    cfg = quest.get("config") or {}
    msgs = cfg.get("messages") or {}
    name = _get(msgs, "questName", "quest_name")
    game = _get(msgs, "gameTitle", "game_title")
    if name and game and str(game).lower() not in str(name).lower():
        return f"{str(name).strip()} ({str(game).strip()})"
    if name:
        return str(name).strip()
    if game:
        return str(game).strip()
    app_name = (cfg.get("application") or {}).get("name")
    if app_name:
        return str(app_name).strip()
    return f"Quest#{quest.get('id', '?')}"


def get_expires_at(quest: dict) -> Optional[str]:
    cfg = quest.get("config") or {}
    return _get(cfg, "expiresAt", "expires_at")


def is_expired(quest: dict) -> bool:
    exp_dt = parse_iso_datetime(get_expires_at(quest))
    if not exp_dt:
        return False
    return exp_dt <= datetime.now(timezone.utc)


def get_user_status(quest: dict) -> dict:
    us = _get(quest, "userStatus", "user_status")
    return us if isinstance(us, dict) else {}


def is_enrolled(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "enrolledAt", "enrolled_at"))


def is_completed(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "completedAt", "completed_at"))


def get_task_type(quest: dict) -> Optional[str]:
    tasks = get_tasks_dict(quest)
    for t in SUPPORTED_TASKS:
        if t in tasks and tasks[t] is not None:
            return t
    if tasks:
        return next(iter(tasks.keys()))
    return None


def get_quest_category(quest: dict) -> str:
    t = (get_task_type(quest) or "").upper()
    if t in VIDEO_TASKS:
        return "VIDEO"
    elif t in GAME_TASKS:
        return "GAME"
    return "MINI_APP"


def is_completable(quest: dict) -> bool:
    """Chỉ nhận và chạy nhiệm vụ VIDEO hoặc GAME còn hạn, bỏ qua hoàn toàn Mini-App."""
    if is_expired(quest):
        return False
    return get_quest_category(quest) in ("VIDEO", "GAME")


def get_category_badge(quest: dict) -> str:
    cat = get_quest_category(quest)
    t = get_task_type(quest) or "UNKNOWN"
    if cat == "VIDEO":
        return f"{Colors.MAGENTA}[VIDEO    | {t}]{Colors.RESET}"
    elif cat == "GAME":
        return f"{Colors.BLUE}[GAME     | {t}]{Colors.RESET}"
    return f"{Colors.DIM}[BỎ QUA   | {t}]{Colors.RESET}"


def get_seconds_needed(quest: dict) -> int:
    tasks = get_tasks_dict(quest)
    task_type = get_task_type(quest)
    if task_type and task_type in tasks:
        task_obj = tasks.get(task_type) or {}
        target = int(task_obj.get("target") or 0)
        if target > 0:
            return target
    return 900


def extract_progress_from_status(us: dict, task_type: Optional[str]) -> float:
    if not isinstance(us, dict):
        return 0.0

    inner_us = _get(us, "userStatus", "user_status")
    if isinstance(inner_us, dict):
        us = inner_us

    progress = _get(us, "progress")
    if isinstance(progress, dict):
        if task_type and task_type in progress:
            node = progress[task_type]
            if isinstance(node, dict) and node.get("value") is not None:
                return float(node["value"])
            elif isinstance(node, (int, float)):
                return float(node)

        max_val = 0.0
        for _, v in progress.items():
            if isinstance(v, dict) and v.get("value") is not None:
                try:
                    max_val = max(max_val, float(v["value"]))
                except Exception:
                    pass
            elif isinstance(v, (int, float)):
                max_val = max(max_val, float(v))
        if max_val > 0:
            return max_val

    sp = _get(us, "streamProgressSeconds", "stream_progress_seconds")
    if sp is not None:
        try:
            return float(sp)
        except Exception:
            pass

    return 0.0


def get_seconds_done(quest: dict) -> float:
    task_type = get_task_type(quest)
    us = get_user_status(quest)
    return extract_progress_from_status(us, task_type)


def get_enrolled_at(quest: dict) -> Optional[str]:
    us = get_user_status(quest)
    return _get(us, "enrolledAt", "enrolled_at")


# ── Bộ Quản lý Nhiệm vụ của Từng Tài khoản ─────────────────────────────────────
class AccountQuestRunner:
    def __init__(self, api: DiscordAPI):
        self.api = api
        self.active_quests: List[dict] = []
        self.expired_count: int = 0
        self.skipped_miniapp_count: int = 0

    def fetch_and_filter_quests(self) -> List[dict]:
        try:
            r = self.api.get("/quests/@me")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    raw_quests = data.get("quests") or []
                elif isinstance(data, list):
                    raw_quests = data
                else:
                    raw_quests = []

                valid_quests = []
                expired = 0
                skipped_miniapp = 0
                for q in raw_quests:
                    if not isinstance(q, dict):
                        continue
                    if is_expired(q):
                        expired += 1
                        continue
                    if not is_completable(q):
                        skipped_miniapp += 1
                        continue
                    valid_quests.append(q)

                self.expired_count = expired
                self.skipped_miniapp_count = skipped_miniapp
                self.active_quests = valid_quests
                return valid_quests

            elif r.status_code == 429:
                try:
                    retry_after = float(r.json().get("retry_after", 5))
                except Exception:
                    retry_after = 5.0
                time.sleep(retry_after + 0.5)
                return self.fetch_and_filter_quests()
            else:
                log(f"[{self.api.username}] Lỗi lấy quest (HTTP {r.status_code})", "warn")
                return []
        except Exception as e:
            log(f"[{self.api.username}] Lỗi kết nối khi lấy quest: {e}", "error")
            return []

    def enroll_quest(self, quest: dict) -> bool:
        name = get_quest_name(quest)
        qid = quest.get("id")
        if not qid:
            return False

        for _ in range(3):
            try:
                r = self.api.post(f"/quests/{qid}/enroll", {
                    "location": 11,
                    "is_targeted": False,
                    "metadata_raw": None,
                    "metadata_sealed": None,
                    "traffic_metadata_raw": quest.get("traffic_metadata_raw"),
                    "traffic_metadata_sealed": quest.get("traffic_metadata_sealed"),
                })
                if r.status_code == 429:
                    wait = float(r.json().get("retry_after", 5)) + 0.5
                    time.sleep(wait)
                    continue
                if r.status_code in (200, 201, 204):
                    log(f"[{self.api.username}] Đã nhận nhiệm vụ: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                    return True
                return False
            except Exception:
                return False
        return False

    def auto_accept_all(self) -> List[dict]:
        if not AUTO_ACCEPT:
            return self.active_quests
        unaccepted = [
            q for q in self.active_quests
            if not is_enrolled(q) and not is_completed(q) and is_completable(q)
        ]
        if not unaccepted:
            return self.active_quests

        log(f"[{self.api.username}] Tự động nhận {len(unaccepted)} nhiệm vụ (VIDEO/GAME)...", "info")
        for q in unaccepted:
            self.enroll_quest(q)
            time.sleep(0.6)
        time.sleep(0.3)
        return self.fetch_and_filter_quests()


# ── Hiển thị Bảng Theo Dõi Nhiều Tài Khoản ─────────────────────────────────────
def show_multi_account_overview(runners: List[AccountQuestRunner]):
    print(f"\n{Colors.BOLD}{Colors.CYAN}" + "=" * 78)
    print("              BẢNG THEO DÕI NHIỀU TÀI KHOẢN (CHỈ VIDEO & GAME)")
    print("=" * 78 + f"{Colors.RESET}")

    for idx, runner in enumerate(runners, 1):
        api = runner.api
        quests = runner.fetch_and_filter_quests()
        completed_q = [q for q in quests if is_completed(q)]
        in_progress_q = [q for q in quests if is_enrolled(q) and not is_completed(q)]
        not_enrolled_q = [q for q in quests if not is_enrolled(q) and not is_completed(q)]

        print(f"\n{Colors.BOLD}[Tài khoản #{idx}] {Colors.GREEN}{api.global_name}{Colors.RESET} (@{api.username} | ID: {api.user_id})")
        print(
            f"  +-- Nhiệm vụ hỗ trợ  : {Colors.BOLD}{len(quests)}{Colors.RESET} "
            f"(Đã lọc bỏ {Colors.RED}{runner.expired_count}{Colors.RESET} hết hạn & "
            f"{Colors.YELLOW}{runner.skipped_miniapp_count}{Colors.RESET} Mini-App)"
        )
        print(
            f"  +-- Thống kê         : Đã xong: {Colors.GREEN}{len(completed_q)}{Colors.RESET} | "
            f"Đang chạy: {Colors.YELLOW}{len(in_progress_q)}{Colors.RESET} | "
            f"Chưa nhận: {Colors.CYAN}{len(not_enrolled_q)}{Colors.RESET}"
        )

        if not quests:
            print(f"  +-- {Colors.DIM}(Không có nhiệm vụ VIDEO hoặc GAME nào khả dụng lúc này){Colors.RESET}")
            continue

        for i, q in enumerate(quests):
            is_last = (i == len(quests) - 1)
            branch = "  `--" if is_last else "  +--"
            sub_branch = "     " if is_last else "  |  "
            name = get_quest_name(q)
            badge = get_category_badge(q)
            done = get_seconds_done(q)
            needed = get_seconds_needed(q)
            comp = is_completed(q)
            pbar = make_progress_bar(done, needed, width=18, completed=comp)

            if comp:
                state = f"{Colors.GREEN}[HOÀN THÀNH]{Colors.RESET}"
            elif is_enrolled(q):
                state = f"{Colors.YELLOW}[ĐANG CHẠY ]{Colors.RESET}"
            else:
                state = f"{Colors.DIM}[CHƯA NHẬN ]{Colors.RESET}"

            print(f"{branch} {state} {badge} {Colors.BOLD}{name}{Colors.RESET}")
            print(f"{sub_branch}   Tiến trình: {pbar}")


# ── Worker Chạy Nhiệm Vụ VIDEO & GAME ──────────────────────────────────────────
class QuestTaskWorker:
    def __init__(self, api: DiscordAPI, quest: dict):
        self.api = api
        self.quest = quest
        self.qid = str(quest.get("id", ""))
        self.name = get_quest_name(quest)
        self.category = get_quest_category(quest)
        self.task_type = get_task_type(quest) or "PLAY_ON_DESKTOP"
        self.seconds_needed = max(1, get_seconds_needed(quest))
        self.seconds_done = get_seconds_done(quest)
        self.completed = is_completed(quest) or (self.seconds_done >= self.seconds_needed and self.seconds_needed > 1)
        self.status_note = "Đang chuẩn bị..."
        self.pid = random.randint(1000, 30000)

        dt = parse_iso_datetime(get_enrolled_at(quest))
        self.enrolled_ts = dt.timestamp() if dt else time.time()

    def sync_live_progress_from_server(self) -> float:
        try:
            r = self.api.get("/quests/@me", timeout=5)
            if r.status_code == 200:
                data = r.json()
                quests = data.get("quests", []) if isinstance(data, dict) else data
                if isinstance(quests, list):
                    for q in quests:
                        if isinstance(q, dict) and str(q.get("id")) == self.qid:
                            srv_done = get_seconds_done(q)
                            if srv_done > self.seconds_done:
                                self.seconds_done = srv_done
                            if is_completed(q) or self.seconds_done >= self.seconds_needed:
                                self.seconds_done = self.seconds_needed
                                self.completed = True
                            return srv_done
        except Exception:
            pass
        return self.seconds_done

    def run(self):
        if self.completed:
            self.seconds_done = self.seconds_needed
            self.status_note = "Đã hoàn thành!"
            return

        if self.category == "VIDEO":
            self._run_video()
        else:
            self._run_game()

    def _run_video(self):
        self.status_note = "Đang chạy tiến trình Video..."
        max_future = 10
        speed = 7
        interval = 1.0

        while self.seconds_done < self.seconds_needed and not self.completed:
            max_allowed = (time.time() - self.enrolled_ts) + max_future
            diff = max_allowed - self.seconds_done
            next_ts = min(float(self.seconds_needed), self.seconds_done + speed)

            if diff >= speed or next_ts >= self.seconds_needed:
                try:
                    payload_ts = min(float(self.seconds_needed), next_ts + random.random() * 0.5)
                    r = self.api.post(f"/quests/{self.qid}/video-progress", {
                        "timestamp": payload_ts
                    })
                    if r.status_code == 200:
                        body = r.json() if r.content else {}
                        self.seconds_done = next_ts
                        self.status_note = "Đang gửi video-progress..."
                        if body.get("completed_at") or self.seconds_done >= self.seconds_needed:
                            self.seconds_done = self.seconds_needed
                            self.completed = True
                            self.status_note = "Hoàn tất Video!"
                            break
                    elif r.status_code == 429:
                        wait = float(r.json().get("retry_after", 5)) + 0.5
                        self.status_note = f"Rate limit ({wait:.0f}s)..."
                        time.sleep(wait)
                        continue
                    else:
                        self.status_note = f"HTTP {r.status_code}"
                except Exception as e:
                    self.status_note = f"Lỗi mạng: {str(e)[:18]}"
            else:
                self.status_note = "Đợi đồng bộ thời gian..."

            time.sleep(interval)

        try:
            self.api.post(f"/quests/{self.qid}/video-progress", {"timestamp": self.seconds_needed})
        except Exception:
            pass
        self.seconds_done = self.seconds_needed
        self.completed = True
        self.status_note = "Hoàn tất Video!"

    def _run_game(self):
        stream_key = f"call:0:{self.pid}"

        while self.seconds_done < self.seconds_needed and not self.completed:
            try:
                r = self.api.post(f"/quests/{self.qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": False,
                })
                if r.status_code == 200:
                    body = r.json() if r.content else {}
                    new_prog = extract_progress_from_status(body, self.task_type)

                    if new_prog > self.seconds_done:
                        self.seconds_done = new_prog
                    else:
                        self.sync_live_progress_from_server()

                    if body.get("completed_at") or self.seconds_done >= self.seconds_needed:
                        self.seconds_done = self.seconds_needed
                        self.completed = True
                        self.status_note = "Hoàn tất Game!"
                        break

                    for sec in range(HEARTBEAT_INTERVAL):
                        if self.completed or self.seconds_done >= self.seconds_needed:
                            break
                        rem_wait = HEARTBEAT_INTERVAL - sec
                        self.status_note = f"Heartbeat tiếp sau {rem_wait}s"
                        time.sleep(1)

                elif r.status_code == 429:
                    wait = float(r.json().get("retry_after", 10)) + 0.5
                    self.status_note = f"Rate limit ({wait:.0f}s)..."
                    time.sleep(wait)
                else:
                    self.status_note = f"HTTP {r.status_code}"
                    time.sleep(5)
            except Exception as e:
                self.status_note = f"Lỗi: {str(e)[:18]}"
                time.sleep(3)

        if self.completed or self.seconds_done >= self.seconds_needed:
            try:
                self.api.post(f"/quests/{self.qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": True,
                })
            except Exception:
                pass
            self.seconds_done = self.seconds_needed
            self.completed = True
            self.status_note = "Hoàn tất Game!"


def run_all_quests_once(runners: List[AccountQuestRunner]):
    print(f"\n{Colors.BOLD}{Colors.CYAN}── ĐANG QUÉT & KHỞI CHẠY NHIỆM VỤ VIDEO & GAME ──{Colors.RESET}")

    workers: List[QuestTaskWorker] = []

    for runner in runners:
        runner.fetch_and_filter_quests()
        quests = runner.auto_accept_all()
        for q in quests:
            if is_enrolled(q) and not is_completed(q) and is_completable(q):
                workers.append(QuestTaskWorker(runner.api, q))

    if not workers:
        log("Không có nhiệm vụ VIDEO hoặc GAME nào cần chạy (Mini-App đã được tự động bỏ qua)!", "ok")
        return

    log(f"Tìm thấy {Colors.BOLD}{len(workers)}{Colors.RESET} nhiệm vụ VIDEO/GAME. Đang xử lý đồng loạt...", "info")
    print()

    threads: List[threading.Thread] = []
    for w in workers:
        t = threading.Thread(target=w.run, daemon=True)
        threads.append(t)
        t.start()

    num_lines = len(workers) + 2

    def render_dashboard(first_draw: bool = False):
        with print_lock:
            if not first_draw:
                sys.stdout.write(f"\033[{num_lines}A")
            done_count = sum(1 for w in workers if w.completed)
            header = (
                f"{Colors.BOLD}TIẾN TRÌNH NHIỆM VỤ ĐANG CHẠY "
                f"({done_count}/{len(workers)} hoàn thành){Colors.RESET}"
            )
            sys.stdout.write(f"\r\033[K{header}\n")
            sys.stdout.write(f"\r\033[K{'-' * 86}\n")
            for w in workers:
                if w.category == "VIDEO":
                    cat_tag = f"{Colors.MAGENTA}[VIDEO]{Colors.RESET}"
                else:
                    cat_tag = f"{Colors.BLUE}[GAME ]{Colors.RESET}"

                pbar = make_progress_bar(w.seconds_done, w.seconds_needed, width=15, completed=w.completed)
                acc_tag = f"{Colors.BOLD}{w.api.username[:10]:<10}{Colors.RESET}"
                q_title = w.name[:20].ljust(20)
                state_str = f"{Colors.GREEN}Xong!{Colors.RESET}" if w.completed else f"{Colors.YELLOW}{w.status_note}{Colors.RESET}"
                line = f" [{acc_tag}] {cat_tag} {q_title} | {pbar} | {state_str}"
                sys.stdout.write(f"\r\033[K{line}\n")
            sys.stdout.flush()

    render_dashboard(first_draw=True)
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            render_dashboard(first_draw=False)
        render_dashboard(first_draw=False)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Đã nhận lệnh dừng từ người dùng (Ctrl+C).{Colors.RESET}")
        return

    done_total = sum(1 for w in workers if w.completed)
    print(f"\n{Colors.GREEN}{Colors.BOLD}[OK] ĐÃ XỬ LÝ XONG ({done_total}/{len(workers)} NHIỆM VỤ HOÀN THÀNH)!{Colors.RESET}\n")


# ── Khởi tạo & Menu Chính ──────────────────────────────────────────────────────
def init_runners(tokens: List[str], build_number: int) -> List[AccountQuestRunner]:
    valid_runners = []
    log(f"Đang kiểm tra {len(tokens)} token...", "info")
    for idx, tok in enumerate(tokens, 1):
        api = DiscordAPI(tok, build_number)
        if api.validate_token():
            log(f"  [#{idx}] Hợp lệ: {Colors.BOLD}{api.global_name}{Colors.RESET} (@{api.username})", "ok")
            valid_runners.append(AccountQuestRunner(api))
        else:
            short_tok = tok[:12] + "..." if len(tok) > 12 else tok
            log(f"  [#{idx}] Token không hợp lệ hoặc đã hết hạn ({short_tok})", "error")
    return valid_runners


def main():
    print(f"{Colors.BOLD}{Colors.CYAN}" + "=" * 76)
    print("  Discord Quest Auto-Completer (Lite Edition: Chỉ chạy VIDEO & GAME)")
    print("=" * 76 + f"{Colors.RESET}")

    tokens = load_tokens(TOKENS_FILE)
    if not tokens and os.path.exists(".token"):
        try:
            with open(".token", "r", encoding="utf-8", errors="ignore") as f:
                old_tok = clean_token(f.read())
                if old_tok:
                    tokens.append(old_tok)
                    save_tokens(tokens, TOKENS_FILE)
        except Exception:
            pass

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        cli_tok = clean_token(sys.argv[1])
        if cli_tok and cli_tok not in tokens:
            tokens.append(cli_tok)
            save_tokens(tokens, TOKENS_FILE)

    if not tokens:
        log(f"Chưa có token nào trong file {TOKENS_FILE}.", "warn")
        tokens = prompt_add_tokens(TOKENS_FILE)

    if not tokens:
        log("Không có token nào được nhập -> Thoát.", "error")
        return

    build_number = fetch_latest_build_number()
    runners = init_runners(tokens, build_number)

    while not runners:
        log("Không có token nào đăng nhập thành công!", "error")
        retry = input(f"{Colors.BOLD}Bạn có muốn nhập lại Token mới không? (y/n): {Colors.RESET}").strip().lower()
        if retry == "y":
            save_tokens([], TOKENS_FILE)
            tokens = prompt_add_tokens(TOKENS_FILE)
            if not tokens:
                return
            runners = init_runners(tokens, build_number)
        else:
            return

    if "--view" in sys.argv:
        show_multi_account_overview(runners)
        return
    if "--once" in sys.argv:
        show_multi_account_overview(runners)
        run_all_quests_once(runners)
        return

    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}---------------- MENU ĐIỀU KHIỂN ----------------{Colors.RESET}")
        print(f"  {Colors.BOLD}1.{Colors.RESET} Xem danh sách tài khoản & tiến trình (Chỉ VIDEO / GAME)")
        print(f"  {Colors.BOLD}2.{Colors.RESET} Tự quét & chạy hết nhiệm vụ VIDEO / GAME (1 lần)")
        print(f"  {Colors.BOLD}3.{Colors.RESET} Nhập thêm Token vào file {Colors.BOLD}{TOKENS_FILE}{Colors.RESET}")
        print(f"  {Colors.BOLD}0.{Colors.RESET} Thoát")
        print(f"{Colors.BOLD}{Colors.CYAN}-------------------------------------------------{Colors.RESET}")

        try:
            choice = input(f"{Colors.BOLD}Chọn chức năng (0-3): {Colors.RESET}").strip() or "1"
        except EOFError:
            break

        if choice == "1":
            show_multi_account_overview(runners)
        elif choice == "2":
            show_multi_account_overview(runners)
            run_all_quests_once(runners)
            break
        elif choice == "3":
            tokens = prompt_add_tokens(TOKENS_FILE)
            runners = init_runners(tokens, build_number)
        elif choice == "0":
            log("Đã thoát chương trình.", "info")
            break
        else:
            log("Lựa chọn không hợp lệ, vui lòng chọn từ 0 đến 3.", "warn")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        log("Đã dừng chương trình.", "info")
    except Exception as e:
        import traceback
        print(f"\n{Colors.RED}[LỖI CHI TIẾT]{Colors.RESET} {e}")
        traceback.print_exc()
        if os.name == "nt":
            input("\nNhấn Enter để đóng cửa sổ...")