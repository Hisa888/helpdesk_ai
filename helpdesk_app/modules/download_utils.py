from __future__ import annotations

from pathlib import Path
import io
import zipfile
import pandas as pd


def _ensure_utf8_sig_csv_bytes(raw: bytes) -> bytes:
    raw = raw or b""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "latin1"):
        try:
            return raw.decode(enc).encode("utf-8-sig")
        except Exception:
            continue
    return b"\xef\xbb\xbf" + raw


def csv_bytes_as_utf8_sig(data) -> bytes:
    if data is None:
        return pd.DataFrame().to_csv(index=False).encode("utf-8-sig")
    if isinstance(data, (bytes, bytearray)):
        return _ensure_utf8_sig_csv_bytes(bytes(data))
    if hasattr(data, "read") and callable(getattr(data, "read")):
        try:
            raw = data.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8-sig")
            return _ensure_utf8_sig_csv_bytes(bytes(raw))
        except Exception:
            pass
    if isinstance(data, (str, Path)):
        candidate = Path(data)
        if candidate.exists() and candidate.is_file():
            return _ensure_utf8_sig_csv_bytes(candidate.read_bytes())
    if isinstance(data, pd.DataFrame):
        df = data
    elif isinstance(data, list):
        if len(data) == 0:
            df = pd.DataFrame()
        elif isinstance(data[0], dict):
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame({"value": data})
    elif isinstance(data, dict):
        df = pd.DataFrame([data])
    else:
        df = pd.DataFrame({"value": [str(data)]})
    return df.to_csv(index=False).encode("utf-8-sig")


def list_log_files(log_dir: Path) -> list[Path]:
    try:
        patterns = ["nohit_*.csv", "candidate_learning_*.csv"]
        files = []
        seen = set()
        for pattern in patterns:
            for p in log_dir.glob(pattern):
                key = str(p.resolve())
                if key not in seen:
                    seen.add(key)
                    files.append(p)
        return sorted(files, reverse=True)
    except Exception:
        return []


def make_logs_zip(files, *, csv_bytes_fn=csv_bytes_as_utf8_sig) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files or []:
            try:
                path_obj = Path(p)
                if str(path_obj).lower().endswith(".csv"):
                    zf.writestr(path_obj.name, csv_bytes_fn(path_obj))
                else:
                    zf.writestr(path_obj.name, path_obj.read_bytes())
            except Exception:
                continue
    return bio.getvalue()
