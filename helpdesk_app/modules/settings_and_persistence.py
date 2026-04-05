from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import base64
import json
import os
import re
import threading


def create_runtime_context(st, requests, base_llm_chat, root_dir: Path | str = ".") -> SimpleNamespace:
    root_dir = Path(root_dir)

    ROOT_DIR = root_dir
    ROOT_FAQ_PATH = ROOT_DIR / "faq.csv"
    DATA_DIR = ROOT_DIR / "runtime_data"
    FAQ_PATH = DATA_DIR / "faq.csv"
    LOG_DIR = DATA_DIR / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    UI_THEME_SETTINGS_PATH = DATA_DIR / "ui_theme_settings.json"
    UI_LAYOUT_SETTINGS_PATH = DATA_DIR / "ui_layout_settings.json"
    LLM_SETTINGS_PATH = DATA_DIR / "llm_settings.json"
    SEARCH_SETTINGS_PATH = DATA_DIR / "search_settings.json"

    def default_ui_theme_settings() -> dict:
        return {
            "sidebar_bg_start": "#0f172a",
            "sidebar_bg_end": "#111827",
            "sidebar_text": "#e5eef8",
            "sidebar_text_muted": "#cbd5e1",
            "sidebar_panel_bg": "rgba(255,255,255,0.04)",
            "sidebar_panel_border": "rgba(255,255,255,0.08)",
            "button_bg": "#1e293b",
            "button_text": "#ffffff",
            "button_border": "#334155",
            "button_hover_bg": "#2563eb",
            "button_hover_text": "#ffffff",
            "button_disabled_bg": "#475569",
            "button_disabled_text": "#ffffff",
            "main_bg_start": "#f0f9ff",
            "main_bg_mid": "#ffffff",
            "main_bg_end": "#f8fafc",
            "card_bg": "rgba(255,255,255,0.88)",
            "card_border": "#e2e8f0",
            "resizer_line": "rgba(148,163,184,0.36)",
            "resizer_knob": "#38bdf8",
        }

    def default_ui_layout_settings() -> dict:
        return {
            "sidebar_width": 360,
            "main_max_width": 1180,
            "main_padding_top": 32,
            "main_padding_bottom": 144,
            "card_radius": 18,
            "card_shadow_blur": 30,
            "card_shadow_alpha": 0.08,
        }

    def _safe_hex_or_rgba(value: object, fallback: str) -> str:
        s = str(value or '').strip()
        if not s:
            return fallback
        if re.match(r'^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$', s):
            return s
        if re.match(r'^rgba?\([^\)]+\)$', s):
            return s
        return fallback

    def _safe_int_range(value: object, fallback: int, min_value: int, max_value: int) -> int:
        try:
            num = int(float(value))
        except Exception:
            num = fallback
        return max(min_value, min(max_value, num))

    def sanitize_ui_theme_settings(data: dict | None) -> dict:
        base = default_ui_theme_settings()
        src = data or {}
        return {key: _safe_hex_or_rgba(src.get(key), fallback) for key, fallback in base.items()}

    def sanitize_ui_layout_settings(data: dict | None) -> dict:
        base = default_ui_layout_settings()
        src = data or {}
        return {
            "sidebar_width": _safe_int_range(src.get("sidebar_width"), base["sidebar_width"], 240, 620),
            "main_max_width": _safe_int_range(src.get("main_max_width"), base["main_max_width"], 760, 2000),
            "main_padding_top": _safe_int_range(src.get("main_padding_top"), base["main_padding_top"], 4, 96),
            "main_padding_bottom": _safe_int_range(src.get("main_padding_bottom"), base["main_padding_bottom"], 72, 280),
            "card_radius": _safe_int_range(src.get("card_radius"), base["card_radius"], 8, 40),
            "card_shadow_blur": _safe_int_range(src.get("card_shadow_blur"), base["card_shadow_blur"], 0, 80),
            "card_shadow_alpha": _safe_int_range(src.get("card_shadow_alpha"), int(base["card_shadow_alpha"] * 100), 0, 40) / 100.0,
        }

    def default_llm_settings() -> dict:
        return {
            "provider": "groq",
            "groq_model": "llama-3.1-8b-instant",
            "ollama_model": "qwen2.5:7b",
            "ollama_base_url": "http://localhost:11434",
        }

    def sanitize_llm_settings(data: dict | None) -> dict:
        base = default_llm_settings()
        src = data or {}
        provider = str(src.get("provider", base["provider"])).strip().lower()
        if provider not in ("groq", "ollama"):
            provider = base["provider"]
        return {
            "provider": provider,
            "groq_model": str(src.get("groq_model", base["groq_model"])).strip() or base["groq_model"],
            "ollama_model": str(src.get("ollama_model", base["ollama_model"])).strip() or base["ollama_model"],
            "ollama_base_url": str(src.get("ollama_base_url", base["ollama_base_url"])).strip() or base["ollama_base_url"],
        }

    def load_json_settings(path_obj: Path, default_factory, sanitizer):
        if path_obj.exists():
            try:
                data = json.loads(path_obj.read_text(encoding='utf-8'))
                return sanitizer(data if isinstance(data, dict) else {})
            except Exception:
                return default_factory()
        return default_factory()

    def _get_setting(key: str, default: str = "") -> str:
        try:
            v = st.secrets.get(key, None)  # type: ignore[attr-defined]
        except Exception:
            v = None
        if v is None:
            v = os.environ.get(key)
        return str(v) if v is not None else default

    COMPANY_NAME = _get_setting("COMPANY_NAME", "株式会社〇〇（デモ）")
    LOGO_PATH = _get_setting("LOGO_PATH", "assets/logo.png")
    CONTACT_URL = _get_setting("CONTACT_URL", "")
    CONTACT_EMAIL = _get_setting("CONTACT_EMAIL", "")

    def build_contact_link() -> str:
        if CONTACT_URL:
            return CONTACT_URL
        if CONTACT_EMAIL:
            return f"mailto:{CONTACT_EMAIL}?subject=情シス問い合わせAI%20導入相談"
        return ""

    PERSIST_MODE = _get_setting("PERSIST_MODE", "local").strip().lower()
    GITHUB_TOKEN = _get_setting("GITHUB_TOKEN", "").strip()
    GITHUB_REPO = _get_setting("GITHUB_REPO", "").strip()
    GITHUB_BRANCH = _get_setting("GITHUB_BRANCH", "main").strip() or "main"
    GITHUB_BASE_PATH = _get_setting("GITHUB_BASE_PATH", "streamlit_data").strip().strip("/")

    def _github_persistence_enabled() -> bool:
        try:
            return str(PERSIST_MODE).strip().lower() == "github" and bool(str(GITHUB_TOKEN).strip() and str(GITHUB_REPO).strip())
        except Exception:
            return False

    def github_persistence_enabled() -> bool:
        return _github_persistence_enabled()

    def persistence_status_text() -> str:
        if _github_persistence_enabled():
            return f"GitHub永続化: ON（{GITHUB_REPO}@{GITHUB_BRANCH} / {GITHUB_BASE_PATH}）"
        return "ローカル保存のみ（Streamlit Cloud の Reboot で消える可能性があります）"

    def _remote_relpath(local_path: Path) -> str:
        try:
            rel = local_path.resolve().relative_to(DATA_DIR.resolve())
        except Exception:
            rel = Path(local_path.name)
        return rel.as_posix()

    def _github_api_url(rel_path: str) -> str:
        rel_path = rel_path.strip("/")
        full_path = f"{GITHUB_BASE_PATH}/{rel_path}" if GITHUB_BASE_PATH else rel_path
        return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{full_path}"

    def _github_headers() -> dict:
        return {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def github_download_file(rel_path: str, local_path: Path) -> bool:
        if not _github_persistence_enabled():
            return False
        try:
            res = requests.get(_github_api_url(rel_path), headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
            if res.status_code != 200:
                return False
            data = res.json()
            content = data.get("content", "")
            encoding = data.get("encoding", "")
            if encoding != "base64" or not content:
                return False
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(base64.b64decode(content))
            return True
        except Exception:
            return False

    def github_upload_file(local_path: Path, rel_path: str | None = None, commit_message: str | None = None) -> bool:
        if not github_persistence_enabled() or not local_path.exists():
            st.error("GitHub保存の前提条件を満たしていません。PERSIST_MODE / GITHUB_TOKEN / GITHUB_REPO / 対象ファイルを確認してください。")
            return False
        rel_path = rel_path or _remote_relpath(local_path)
        try:
            existing_sha = None
            get_res = requests.get(_github_api_url(rel_path), headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
            if get_res.status_code == 200:
                existing_sha = get_res.json().get("sha")
            elif get_res.status_code not in (200, 404):
                st.error(f"GitHub API error (GET): {get_res.status_code}")
                st.code(get_res.text)
                st.caption(f"保存先: {GITHUB_REPO}@{GITHUB_BRANCH} / {GITHUB_BASE_PATH}/{rel_path}")
                return False

            payload = {
                "message": commit_message or f"Update {rel_path} from Streamlit app",
                "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
                "branch": GITHUB_BRANCH,
            }
            if existing_sha:
                payload["sha"] = existing_sha
            put_res = requests.put(_github_api_url(rel_path), headers=_github_headers(), json=payload, timeout=25)
            if put_res.status_code not in (200, 201):
                st.error(f"GitHub API error (PUT): {put_res.status_code}")
                st.code(put_res.text)
                st.caption(f"保存先: {GITHUB_REPO}@{GITHUB_BRANCH} / {GITHUB_BASE_PATH}/{rel_path}")
                return False
            return True
        except Exception as e:
            st.error("GitHub保存エラー")
            st.exception(e)
            st.caption(f"保存先: {GITHUB_REPO}@{GITHUB_BRANCH} / {GITHUB_BASE_PATH}/{rel_path}")
            return False

    def github_list_dir(rel_dir: str) -> list[str]:
        if not _github_persistence_enabled():
            return []
        try:
            res = requests.get(_github_api_url(rel_dir), headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
            if res.status_code != 200:
                return []
            data = res.json()
            if not isinstance(data, list):
                return []
            return [str(item.get("path", "")) for item in data if item.get("type") == "file"]
        except Exception:
            return []

    def bootstrap_persistent_storage():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if not FAQ_PATH.exists() and ROOT_FAQ_PATH.exists():
            try:
                FAQ_PATH.write_bytes(ROOT_FAQ_PATH.read_bytes())
            except Exception:
                pass
        if _github_persistence_enabled():
            github_download_file("faq.csv", FAQ_PATH)
            for remote_path in github_list_dir("logs"):
                if not remote_path.endswith('.csv'):
                    continue
                github_download_file(f"logs/{Path(remote_path).name}", LOG_DIR / Path(remote_path).name)

    def _github_upload_file_quiet(local_path: Path, rel_path: str | None = None, commit_message: str | None = None) -> bool:
        if not _github_persistence_enabled() or not local_path.exists():
            return False
        rel_path = rel_path or _remote_relpath(local_path)
        try:
            existing_sha = None
            get_res = requests.get(_github_api_url(rel_path), headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=8)
            if get_res.status_code == 200:
                existing_sha = get_res.json().get("sha")
            elif get_res.status_code not in (200, 404):
                return False

            payload = {
                "message": commit_message or f"Update {rel_path} from Streamlit app",
                "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
                "branch": GITHUB_BRANCH,
            }
            if existing_sha:
                payload["sha"] = existing_sha
            put_res = requests.put(_github_api_url(rel_path), headers=_github_headers(), json=payload, timeout=8)
            return put_res.status_code in (200, 201)
        except Exception:
            return False

    def persist_runtime_file(local_path: Path, label: str = "data") -> bool:
        if not local_path.exists():
            return False
        if not _github_persistence_enabled():
            return True
        rel_path = _remote_relpath(local_path)
        msg = f"Update {label}: {rel_path}"
        return github_upload_file(local_path, rel_path=rel_path, commit_message=msg)

    def persist_runtime_file_async(local_path: Path, label: str = "data") -> bool:
        if not local_path.exists():
            return False
        if not _github_persistence_enabled():
            return True
        rel_path = _remote_relpath(local_path)
        msg = f"Update {label}: {rel_path}"

        def _worker():
            _github_upload_file_quiet(local_path, rel_path=rel_path, commit_message=msg)

        try:
            threading.Thread(target=_worker, daemon=True).start()
            return True
        except Exception:
            return False

    def persist_faq_now() -> bool:
        return persist_runtime_file(FAQ_PATH, label="faq")

    def persist_log_now(path: Path) -> bool:
        return persist_runtime_file_async(path, label="log")

    def save_json_settings(path_obj: Path, settings: dict, label: str) -> tuple[bool, dict]:
        try:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
            ok = persist_runtime_file(path_obj, label=label)
            return ok, settings
        except Exception:
            return False, settings

    LLM_SETTINGS = load_json_settings(LLM_SETTINGS_PATH, default_llm_settings, sanitize_llm_settings)

    def current_llm_settings() -> dict:
        base = st.session_state.get("llm_settings", LLM_SETTINGS)
        return sanitize_llm_settings(base if isinstance(base, dict) else {})

    def current_llm_provider() -> str:
        return current_llm_settings().get("provider", "groq")

    def save_llm_settings(settings: dict) -> tuple[bool, dict]:
        clean = sanitize_llm_settings(settings)
        return save_json_settings(LLM_SETTINGS_PATH, clean, "llm_settings")

    def _ollama_chat(messages, model: str, base_url: str) -> str:
        url = str(base_url or "http://localhost:11434").rstrip("/") + "/api/chat"
        payload = {"model": model or "qwen2.5:7b", "messages": messages, "stream": False}
        resp = requests.post(url, json=payload, timeout=(5, 120))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, dict) and msg.get("content") is not None:
                return str(msg.get("content")).strip()
            if data.get("response") is not None:
                return str(data.get("response")).strip()
        return ""

    def llm_chat(messages):
        cfg = current_llm_settings()
        provider = cfg.get("provider", "groq")
        if provider == "ollama":
            try:
                return _ollama_chat(messages=messages, model=cfg.get("ollama_model", "qwen2.5:7b"), base_url=cfg.get("ollama_base_url", "http://localhost:11434"))
            except Exception as e:
                st.warning(f"Ollama接続に失敗したためGroqに切り替えます: {e}")
        return base_llm_chat(messages)

    DEFAULT_SEARCH_THRESHOLD = 0.42
    DEFAULT_SUGGEST_THRESHOLD = 0.26

    def _safe_float_range(value: object, fallback: float, min_value: float, max_value: float) -> float:
        try:
            num = float(value)
        except Exception:
            num = fallback
        return max(min_value, min(max_value, num))

    def _safe_bool(value: object, fallback: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return fallback
        s = str(value).strip().lower()
        if s in {"1", "true", "yes", "on", "y"}:
            return True
        if s in {"0", "false", "no", "off", "n"}:
            return False
        return fallback

    def default_search_settings() -> dict:
        return {
            "answer_threshold": DEFAULT_SEARCH_THRESHOLD,
            "suggest_threshold": DEFAULT_SUGGEST_THRESHOLD,
            "word_weight": 0.54,
            "char_weight": 0.46,
            "exact_bonus": 0.28,
            "contains_bonus": 0.14,
            "token_bonus_max": 0.24,
            "concept_bonus_max": 0.24,
            "prefix_bonus": 0.07,
            "semantic_enabled": True,
            "semantic_boost": 0.28,
            "semantic_candidate_count": 8,
            "semantic_min_query_len": 8,
            "semantic_trigger_min": 0.24,
            "semantic_trigger_max": 0.48,
            "semantic_skip_fastlane": True,
            "top_k": 3,
        }

    def _sanitize_search_settings(data: dict | None) -> dict:
        base = default_search_settings()
        src = data or {}
        answer = _safe_float_range(src.get("answer_threshold", base["answer_threshold"]), base["answer_threshold"], 0.10, 1.20)
        suggest = _safe_float_range(src.get("suggest_threshold", base["suggest_threshold"]), base["suggest_threshold"], 0.05, 1.20)
        if suggest > answer:
            suggest = max(0.05, round(answer - 0.05, 2))
        word_weight_raw = _safe_float_range(src.get("word_weight", base["word_weight"]), base["word_weight"], 0.0, 1.0)
        char_weight_raw = _safe_float_range(src.get("char_weight", base["char_weight"]), base["char_weight"], 0.0, 1.0)
        weight_total = word_weight_raw + char_weight_raw
        if weight_total <= 0:
            word_weight = base["word_weight"]
            char_weight = base["char_weight"]
        else:
            word_weight = round(word_weight_raw / weight_total, 2)
            char_weight = round(1.0 - word_weight, 2)
        exact_bonus = _safe_float_range(src.get("exact_bonus", base["exact_bonus"]), base["exact_bonus"], 0.0, 0.8)
        contains_bonus = _safe_float_range(src.get("contains_bonus", base["contains_bonus"]), base["contains_bonus"], 0.0, 0.6)
        token_bonus_max = _safe_float_range(src.get("token_bonus_max", base["token_bonus_max"]), base["token_bonus_max"], 0.0, 0.8)
        concept_bonus_max = _safe_float_range(src.get("concept_bonus_max", base["concept_bonus_max"]), base["concept_bonus_max"], 0.0, 0.8)
        prefix_bonus = _safe_float_range(src.get("prefix_bonus", base["prefix_bonus"]), base["prefix_bonus"], 0.0, 0.3)
        semantic_enabled = _safe_bool(src.get("semantic_enabled", base["semantic_enabled"]), base["semantic_enabled"])
        semantic_boost = _safe_float_range(src.get("semantic_boost", base["semantic_boost"]), base["semantic_boost"], 0.0, 0.8)
        semantic_candidate_count = int(round(_safe_float_range(src.get("semantic_candidate_count", base["semantic_candidate_count"]), base["semantic_candidate_count"], 1, 20)))
        semantic_min_query_len = int(round(_safe_float_range(src.get("semantic_min_query_len", base["semantic_min_query_len"]), base["semantic_min_query_len"], 1, 50)))
        semantic_trigger_min = _safe_float_range(src.get("semantic_trigger_min", base["semantic_trigger_min"]), base["semantic_trigger_min"], 0.0, 1.2)
        semantic_trigger_max = _safe_float_range(src.get("semantic_trigger_max", base["semantic_trigger_max"]), base["semantic_trigger_max"], 0.0, 1.5)
        if semantic_trigger_max < semantic_trigger_min:
            semantic_trigger_max = semantic_trigger_min
        semantic_skip_fastlane = _safe_bool(src.get("semantic_skip_fastlane", base["semantic_skip_fastlane"]), base["semantic_skip_fastlane"])
        top_k = int(round(_safe_float_range(src.get("top_k", base["top_k"]), base["top_k"], 1, 5)))
        return {
            "answer_threshold": round(answer, 2),
            "suggest_threshold": round(suggest, 2),
            "word_weight": round(word_weight, 2),
            "char_weight": round(char_weight, 2),
            "exact_bonus": round(exact_bonus, 2),
            "contains_bonus": round(contains_bonus, 2),
            "token_bonus_max": round(token_bonus_max, 2),
            "concept_bonus_max": round(concept_bonus_max, 2),
            "prefix_bonus": round(prefix_bonus, 2),
            "semantic_enabled": semantic_enabled,
            "semantic_boost": round(semantic_boost, 2),
            "semantic_candidate_count": semantic_candidate_count,
            "semantic_min_query_len": semantic_min_query_len,
            "semantic_trigger_min": round(semantic_trigger_min, 2),
            "semantic_trigger_max": round(semantic_trigger_max, 2),
            "semantic_skip_fastlane": semantic_skip_fastlane,
            "top_k": top_k,
        }

    def load_search_settings() -> dict:
        if SEARCH_SETTINGS_PATH.exists():
            try:
                data = json.loads(SEARCH_SETTINGS_PATH.read_text(encoding="utf-8"))
                return _sanitize_search_settings(data if isinstance(data, dict) else {})
            except Exception:
                return default_search_settings()
        return default_search_settings()

    bootstrap_persistent_storage()
    if _github_persistence_enabled():
        github_download_file("search_settings.json", SEARCH_SETTINGS_PATH)
    SEARCH_SETTINGS = load_search_settings()
    if _github_persistence_enabled():
        github_download_file("ui_theme_settings.json", UI_THEME_SETTINGS_PATH)
        github_download_file("ui_layout_settings.json", UI_LAYOUT_SETTINGS_PATH)
    UI_THEME_SETTINGS = sanitize_ui_theme_settings(load_json_settings(UI_THEME_SETTINGS_PATH, default_ui_theme_settings, sanitize_ui_theme_settings))
    UI_LAYOUT_SETTINGS = sanitize_ui_layout_settings(load_json_settings(UI_LAYOUT_SETTINGS_PATH, default_ui_layout_settings, sanitize_ui_layout_settings))

    def current_search_settings() -> dict:
        base = st.session_state.get("search_settings", SEARCH_SETTINGS)
        return _sanitize_search_settings(base if isinstance(base, dict) else {})

    def save_search_settings(answer_threshold: float | None = None, suggest_threshold: float | None = None, extra_settings: dict | None = None) -> tuple[bool, dict]:
        payload = current_search_settings()
        if answer_threshold is not None:
            payload["answer_threshold"] = answer_threshold
        if suggest_threshold is not None:
            payload["suggest_threshold"] = suggest_threshold
        if extra_settings:
            payload.update(extra_settings)
        settings = _sanitize_search_settings(payload)
        try:
            SEARCH_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SEARCH_SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            ok = persist_runtime_file(SEARCH_SETTINGS_PATH, label="search_settings")
            st.session_state["search_settings"] = settings
            return ok, settings
        except Exception:
            st.session_state["search_settings"] = settings
            return False, settings

    def current_ui_theme_settings() -> dict:
        base = st.session_state.get("ui_theme_settings", UI_THEME_SETTINGS)
        return sanitize_ui_theme_settings(base)

    def current_ui_layout_settings() -> dict:
        base = st.session_state.get("ui_layout_settings", UI_LAYOUT_SETTINGS)
        return sanitize_ui_layout_settings(base)

    def save_ui_theme_settings(settings: dict) -> tuple[bool, dict]:
        clean = sanitize_ui_theme_settings(settings)
        ok, saved = save_json_settings(UI_THEME_SETTINGS_PATH, clean, label="ui_theme_settings")
        st.session_state["ui_theme_settings"] = saved
        return ok, saved

    def save_ui_layout_settings(settings: dict) -> tuple[bool, dict]:
        clean = sanitize_ui_layout_settings(settings)
        ok, saved = save_json_settings(UI_LAYOUT_SETTINGS_PATH, clean, label="ui_layout_settings")
        st.session_state["ui_layout_settings"] = saved
        return ok, saved

    def current_search_threshold() -> float:
        try:
            return float(current_search_settings().get("answer_threshold", DEFAULT_SEARCH_THRESHOLD))
        except Exception:
            return DEFAULT_SEARCH_THRESHOLD

    def current_suggest_threshold() -> float:
        try:
            answer = current_search_threshold()
            suggest = float(current_search_settings().get("suggest_threshold", DEFAULT_SUGGEST_THRESHOLD))
            return min(suggest, max(0.05, answer - 0.05))
        except Exception:
            return DEFAULT_SUGGEST_THRESHOLD

    return SimpleNamespace(**locals())
