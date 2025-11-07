"""In-process Vale harness tailored for rule development tests."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import typing as typ
from pathlib import Path

import msgspec
import msgspec.json as msgspec_json

if typ.TYPE_CHECKING:
    from types import TracebackType


IniLike = str | os.PathLike[str] | typ.Mapping[str, typ.Any]
StylesLike = Path | typ.Mapping[str, str | bytes]


class ValedateError(RuntimeError):
    """Base exception for harness failures."""


class InvalidIniSectionError(ValedateError):
    """Raised when a pseudo-section does not map to key/value content."""

    def __init__(self, section: str) -> None:
        super().__init__(f"Section {section!r} must map to a dict of key/value pairs.")


class UnsupportedIniInputError(ValedateError):
    """Raised when the ini argument is of an unsupported type."""

    def __init__(self) -> None:
        super().__init__("ini must be a path, raw ini string, or mapping")


class StylesTreeMissingError(ValedateError):
    """Raised when the requested styles directory is absent."""

    def __init__(self, styles: Path) -> None:
        super().__init__(f"Styles tree {styles} doesn't exist")


class StylesTreeTypeError(ValedateError):
    """Raised when the styles argument resolves to a non-directory."""

    def __init__(self, styles: Path) -> None:
        super().__init__(f"Styles tree {styles} must be a directory")


class ValeExecutionError(ValedateError):
    """Raised when Vale returns a runtime failure."""

    def __init__(self, exit_code: int, stderr: str) -> None:
        super().__init__(f"Vale failed with exit code {exit_code}")
        self.exit_code = exit_code
        self.stderr = stderr


class ValeBinaryNotFoundError(FileNotFoundError, ValedateError):
    """Raised when the Vale executable cannot be located."""

    def __init__(self, binary: str) -> None:
        message = (
            f"Couldn't find '{binary}' on PATH. Install Vale or set vale_bin "
            "explicitly."
        )
        super().__init__(message)


class ValeAction(msgspec.Struct, kw_only=True):
    """Typed view of Vale's optional Action payload."""

    name: str | None = msgspec.field(default=None, name="Name")
    params: list[str] | None = msgspec.field(default=None, name="Params")


class ValeDiagnostic(msgspec.Struct, kw_only=True):
    """Typed representation of Vale's core.Alert JSON output."""

    check: str = msgspec.field(name="Check")
    message: str = msgspec.field(name="Message")
    severity: str = msgspec.field(name="Severity")
    line: int = msgspec.field(name="Line")
    span: tuple[int, int] = msgspec.field(default=(0, 0), name="Span")
    link: str | None = msgspec.field(default=None, name="Link")
    description: str | None = msgspec.field(default=None, name="Description")
    match: str | None = msgspec.field(default=None, name="Match")
    action: ValeAction | None = msgspec.field(default=None, name="Action")


def _which_vale(vale_bin: str) -> str:
    path = shutil.which(vale_bin)
    if path is None:
        raise ValeBinaryNotFoundError(vale_bin)
    return path


def _as_ini_text(ini: IniLike) -> str:
    """Normalise .vale.ini input into a text blob."""
    if isinstance(ini, (str, os.PathLike)):
        candidate = Path(os.fspath(ini))
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
        if isinstance(ini, str):
            return ini

    if isinstance(ini, typ.Mapping):
        lines: list[str] = []

        def _emit_section(body: typ.Mapping[str, typ.Any]) -> None:
            for key, value in body.items():
                if isinstance(value, (list, tuple)):
                    rendered = ", ".join(map(str, value))
                else:
                    rendered = str(value)
                lines.append(f"{key} = {rendered}")

        root = ini.get("__root__", ini.get("top", {}))
        if isinstance(root, typ.Mapping):
            _emit_section(root)

        for section, body in ini.items():
            if section in {"__root__", "top"}:
                continue
            header = section if str(section).startswith("[") else f"[{section}]"
            lines.append("")
            if not isinstance(body, typ.Mapping):
                raise InvalidIniSectionError(str(section))
            lines.append(header)
            _emit_section(body)

        return "\n".join(lines).strip() + "\n"

    raise UnsupportedIniInputError


def _force_styles_path(ini_text: str, styles_dirname: str = "styles") -> str:
    pattern = r"(?m)^\s*StylesPath\s*=.*$"
    if re.search(pattern, ini_text):
        return re.sub(pattern, f"StylesPath = {styles_dirname}", ini_text)
    return f"StylesPath = {styles_dirname}\n{ini_text}"


def _materialise_tree(root: Path, mapping: typ.Mapping[str, str | bytes]) -> None:
    for rel_path, contents in mapping.items():
        destination = root / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            destination.write_bytes(contents)
        else:
            destination.write_text(contents, encoding="utf-8")


def _copy_styles_into(dst: Path, styles: Path) -> None:
    if not styles.exists():
        raise StylesTreeMissingError(styles)
    if not styles.is_dir():
        raise StylesTreeTypeError(styles)
    for item in styles.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _decode_vale_json(stdout: str) -> dict[str, list[ValeDiagnostic]]:
    value = msgspec_json.decode(stdout)

    def _to_alerts(seq: object) -> list[ValeDiagnostic]:
        return msgspec.convert(seq, type=list[ValeDiagnostic])

    if isinstance(value, dict):
        return {str(path): _to_alerts(alerts) for path, alerts in value.items()}

    if isinstance(value, list):
        if value and isinstance(value[0], dict) and {"Path", "Alerts"} <= set(value[0]):
            output: dict[str, list[ValeDiagnostic]] = {}
            for file_obj in value:
                path = str(file_obj["Path"])
                output[path] = _to_alerts(file_obj["Alerts"])
            return output
        return {"<stdin>": _to_alerts(value)}

    return {}


class Valedate:
    """Temporary Vale environment for deterministic rule tests."""

    def __init__(
        self,
        ini: IniLike,
        *,
        styles: StylesLike | None = None,
        vale_bin: str = "vale",
        stdin_ext: str = ".md",
        auto_sync: bool = False,
        min_alert_level: str | None = None,
    ) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="valedate-")
        self.root = Path(self._tmp.name)
        self.vale_bin = _which_vale(vale_bin)
        self.stdin_ext = stdin_ext
        self.default_min_level = min_alert_level

        styles_dir = self.root / "styles"
        styles_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(styles, typ.Mapping):
            _materialise_tree(styles_dir, styles)
        elif isinstance(styles, Path):
            _copy_styles_into(styles_dir, styles)

        ini_text = _force_styles_path(_as_ini_text(ini), styles_dirname="styles")
        self.ini_path = self.root / ".vale.ini"
        self.ini_path.write_text(ini_text, encoding="utf-8")

        if auto_sync and re.search(r"(?m)^\s*Packages\s*=", ini_text):
            self._run(["sync"])

    def lint(
        self,
        text: str,
        *,
        ext: str | None = None,
        min_alert_level: str | None = None,
    ) -> typ.Sequence[ValeDiagnostic]:
        """Lint a string, returning diagnostics for the synthetic <stdin> file."""
        args = [
            "--no-global",
            "--no-exit",
            "--output=JSON",
            f"--ext={ext or self.stdin_ext}",
        ]
        level = min_alert_level or self.default_min_level
        if level is not None:
            args.append(f"--minAlertLevel={level}")
        output = self._run(args, stdin=text)
        by_file = _decode_vale_json(output)
        return next(iter(by_file.values()), [])

    def lint_path(
        self,
        path: Path,
        *,
        min_alert_level: str | None = None,
    ) -> dict[str, list[ValeDiagnostic]]:
        """Lint a file or directory path, returning alerts keyed by path."""
        args = ["--no-global", "--no-exit", "--output=JSON"]
        level = min_alert_level or self.default_min_level
        if level is not None:
            args.append(f"--minAlertLevel={level}")
        output = self._run([*args, str(path)])
        return _decode_vale_json(output)

    def __enter__(self) -> Valedate:
        """Return self to support usage in with-statements."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ensure the temporary tree is removed when leaving the context."""
        self.cleanup()

    def cleanup(self) -> None:
        """Remove the temporary working tree created for this harness."""
        self._tmp.cleanup()

    def _run(self, args: list[str], stdin: str | None = None) -> str:
        cmd = [self.vale_bin, f"--config={self.ini_path}", *args]
        proc = subprocess.run(  # noqa: S603 - we intentionally shell out to Vale
            cmd,
            cwd=self.root,
            input=stdin.encode("utf-8") if stdin is not None else None,
            capture_output=True,
            check=False,
        )
        if proc.returncode >= 2:
            stderr = proc.stderr.decode("utf-8", "replace")
            raise ValeExecutionError(proc.returncode, stderr)
        return proc.stdout.decode("utf-8", "replace")


__all__ = ["ValeAction", "ValeDiagnostic", "Valedate"]
