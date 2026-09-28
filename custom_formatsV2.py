# -*- coding: utf-8 -*-
"""
custom_formats.py — Единый модуль для работы с пользовательскими форматами.
Расширен до 20 форматов: существующие + новые заглушки.
Совместимость: Python 3.9+
Зависимости: только стандартная библиотека.
"""

from __future__ import annotations

import os
import re
import json
import hashlib
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict


# =====================================================================
# 1. .luna — лёгкий формат для программирования / конфигов (уже есть)
# =====================================================================
@dataclass
class LunaConfig:
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "LunaConfig":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Файл не найден: {p}")
        cfg = cls()
        current_section: Optional[str] = None

        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                cfg.data[current_section] = {}
                continue
            if ": " in line:
                key, _, value = line.partition(": ")
                key = key.strip()
                value = value.strip()
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
                elif value.isdigit():
                    value = int(value)
                elif _is_float(value):
                    value = float(value)
                if current_section:
                    cfg.data[current_section][key] = value
                else:
                    cfg.data[key] = value
        return cfg

    def save(self, path: str | Path) -> None:
        p = Path(path)
        lines: List[str] = []
        for key, value in self.data.items():
            if isinstance(value, dict):
                lines.append(f"[{key}]")
                for k, v in value.items():
                    lines.append(f"  {k}: {_format_value(v)}")
                lines.append("")
            else:
                lines.append(f"{key}: {_format_value(value)}")
        p.write_text("\n".join(lines), encoding="utf-8")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)


def _is_float(val: str) -> bool:
    try:
        float(val)
        return True
    except ValueError:
        return False


def _format_value(val: Any) -> str:
    if isinstance(val, list):
        return "[" + ", ".join(str(v) for v in val) + "]"
    return str(val)


# =====================================================================
# 2. .unkn — авто-определение языка и переименование (уже есть)
# =====================================================================
_LANG_SIGNATURES = [
    ("py", [r"^#!.*python", r"^\s*def\s+\w+\(", r"^\s*import\s+\w+", r"^\s*from\s+\w+\s+import"]),
    ("rs", [r"^\s*fn\s+\w+\(", r"^\s*use\s+\w+::", r"^\s*pub\s+(fn|struct|enum)\s+\w+"]),
    ("lua", [r"^\s*local\s+\w+\s*=", r"^\s*function\s+\w+\(", r"^\s*require\s*[\(\"]"]),
    ("js", [r"^\s*const\s+\w+\s*=", r"^\s*function\s+\w+\(", r"^\s*import\s+.*from\s+"]),
    ("c", [r"^\s*#include\s*<", r"^\s*int\s+main\s*\("]),
    ("cpp", [r"^\s*#include\s*<", r"^\s*std::", r"^\s*class\s+\w+\s*\{"]),
    ("go", [r"^\s*package\s+\w+", r"^\s*func\s+\w+\(", r"^\s*import\s+\("]),
    ("sh", [r"^#!/bin/(ba)?sh", r"^\s*echo\s+"]),
    ("java", [r"^\s*public\s+(class|static|void)\s+", r"^\s*import\s+java\."]),
]

_LUAJIT_MARKERS = ["jit", "luajit", "ffi.cdef", "ffi.C"]


def detect_language(content: str) -> str:
    for marker in _LUAJIT_MARKERS:
        if marker in content:
            return "lujit"
    for lang, patterns in _LANG_SIGNATURES:
        score = 0
        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE):
                score += 1
        if score >= 2:
            return lang
    for lang, patterns in _LANG_SIGNATURES:
        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE):
                return lang
    return "txt"


def process_unkn(path: str | Path, dry_run: bool = False) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {p}")
    content = p.read_text(encoding="utf-8", errors="replace")
    lang = detect_language(content)
    ext_map = {
        "py": "py", "rs": "rs", "lua": "lua", "lujit": "lujit",
        "js": "js", "c": "c", "cpp": "cpp", "go": "go",
        "sh": "sh", "java": "java", "txt": "txt",
    }
    new_ext = ext_map.get(lang, "txt")
    new_path = p.with_suffix(f".{new_ext}")
    if dry_run:
        print(f"[DRY RUN] {p.name} -> {new_path.name} (язык: {lang})")
    else:
        p.rename(new_path)
        print(f"[OK] {p.name} -> {new_path.name} (язык: {lang})")
    return str(new_path)


def process_unkn_folder(folder: str | Path, dry_run: bool = False) -> List[str]:
    f = Path(folder)
    results: List[str] = []
    for fpath in f.iterdir():
        if fpath.suffix == ".unkn":
            results.append(process_unkn(fpath, dry_run))
    return results


# =====================================================================
# 3. .pyru — слияние Python и Rust в одном файле (уже есть)
# =====================================================================
_PYRU_PYTHON_MARKER = "# === PYTHON ==="
_PYRU_RUST_MARKER = "# === RUST ==="
_PYRU_END_MARKER = "# === END ==="


def create_pyru(python_code: str, rust_code: str, path: str | Path) -> None:
    p = Path(path)
    content = f"""{_PYRU_PYTHON_MARKER}
{python_code}
{_PYRU_END_MARKER}
{_PYRU_RUST_MARKER}
{rust_code}
{_PYRU_END_MARKER}
"""
    p.write_text(content.strip() + "\n", encoding="utf-8")


def parse_pyru(path: str | Path) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {p}")
    content = p.read_text(encoding="utf-8")
    result: Dict[str, str] = {"python": "", "rust": ""}
    current_block: Optional[str] = None
    block_lines: List[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == _PYRU_PYTHON_MARKER:
            current_block = "python"
            block_lines = []
            continue
        elif stripped == _PYRU_RUST_MARKER:
            if current_block:
                result[current_block] = "\n".join(block_lines).strip()
            current_block = "rust"
            block_lines = []
            continue
        elif stripped == _PYRU_END_MARKER:
            if current_block:
                result[current_block] = "\n".join(block_lines).strip()
            current_block = None
            block_lines = []
            continue
        if current_block:
            block_lines.append(line)
    if current_block and block_lines:
        result[current_block] = "\n".join(block_lines).strip()
    return result


def run_pyru(
    path: str | Path,
    python_executable: str = "python",
    rust_compiler: str = "rustc",
    temp_dir: str | Path = ".pyru_temp",
) -> Dict[str, Any]:
    parts = parse_pyru(path)
    result: Dict[str, Any] = {"python_output": "", "rust_output": "", "rust_compiled": False}

    if parts["python"]:
        proc = subprocess.run(
            [python_executable, "-c", parts["python"]],
            capture_output=True, text=True, timeout=30,
        )
        result["python_output"] = proc.stdout + proc.stderr

    if parts["rust"]:
        tmp = Path(temp_dir)
        tmp.mkdir(exist_ok=True)
        rs_file = tmp / "_pyru_rust.rs"
        rs_file.write_text(parts["rust"], encoding="utf-8")
        exe_file = tmp / "_pyru_rust"
        compile_proc = subprocess.run(
            [rust_compiler, "-o", str(exe_file), str(rs_file)],
            capture_output=True, text=True, timeout=60,
        )
        if compile_proc.returncode == 0:
            result["rust_compiled"] = True
            run_proc = subprocess.run(
                [str(exe_file)],
                capture_output=True, text=True, timeout=30,
            )
            result["rust_output"] = run_proc.stdout + run_proc.stderr
        else:
            result["rust_output"] = f"[Ошибка компиляции]\n{compile_proc.stderr}"
    return result


# =====================================================================
# 4. .lujit — запуск LuaJIT-файлов (уже есть)
# =====================================================================
def is_lujit_file(path: str | Path) -> bool:
    return Path(path).suffix == ".lujit"


def run_lujit(
    path: str | Path,
    luajit_executable: str = "luajit",
    fallback_to_lua: bool = False,
    lua_executable: str = "lua",
) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {p}")
    if not is_lujit_file(p):
        raise ValueError(f"Ожидался .lujit файл, получено: {p.suffix}")

    lujit_path = shutil.which(luajit_executable)
    if lujit_path:
        proc = subprocess.run(
            [lujit_path, str(p)],
            capture_output=True, text=True, timeout=60,
        )
        return {
            "runner": "luajit",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    elif fallback_to_lua:
        lua_path = shutil.which(lua_executable)
        if lua_path:
            proc = subprocess.run(
                [lua_path, str(p)],
                capture_output=True, text=True, timeout=60,
            )
            return {
                "runner": "lua (fallback)",
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "warning": "LuaJIT не найден, использован обычный Lua",
            }
    return {
        "runner": "none",
        "returncode": -1,
        "stdout": "",
        "stderr": "LuaJIT не найден в системе",
    }


def validate_lujit(path: str | Path) -> tuple[bool, str]:
    p = Path(path)
    content = p.read_text(encoding="utf-8", errors="replace")
    jit_features = []
    if "ffi." in content:
        jit_features.append("ffi")
    if "jit." in content:
        jit_features.append("jit")
    if "require('ffi')" in content or 'require("ffi")' in content:
        jit_features.append("require ffi")

    if jit_features:
        return True, f"Найдены LuaJIT-фичи: {', '.join(jit_features)}. Обычный Lua не подойдёт."
    return True, "LuaJIT-специфичных конструкций не найдено. Можно запустить и на обычном Lua."


# =====================================================================
# 5. .acf — манифест критического exe-файла (уже есть)
# =====================================================================
@dataclass
class AcfManifest:
    exe_name: str
    version: str = "1.0.0"
    critical: bool = True
    description: str = ""
    expected_sha256: str = ""
    min_os_version: str = ""
    requires_admin: bool = False
    auto_restart: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exe_name": self.exe_name,
            "version": self.version,
            "critical": self.critical,
            "description": self.description,
            "expected_sha256": self.expected_sha256,
            "min_os_version": self.min_os_version,
            "requires_admin": self.requires_admin,
            "auto_restart": self.auto_restart,
        }

    @classmethod
    def load(cls, path: str | Path) -> "AcfManifest":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(**data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def verify_exe(self, exe_dir: str | Path) -> tuple[bool, str]:
        exe_path = Path(exe_dir) / self.exe_name
        if not exe_path.exists():
            return False, f"EXE не найден: {exe_path}"
        if self.expected_sha256:
            sha = hashlib.sha256(exe_path.read_bytes()).hex
