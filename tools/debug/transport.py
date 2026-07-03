"""Install the EFW LiteTune board transport template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TransportTemplateResult:
    source: Path
    output: Path
    protocol: str
    transport: str
    created: bool


def framework_root() -> Path:
    return Path(__file__).resolve().parents[2]


def transport_template_source() -> Path:
    return framework_root() / "examples" / "debug" / "efw_litetune_transport_port.c"


def install_transport_template(output: str | Path, *, protocol: str = "litetune", transport: str = "uart", force: bool = False) -> TransportTemplateResult:
    protocol = protocol.lower().replace("_", "-")
    transport = transport.lower().replace("_", "-")
    if protocol != "litetune":
        raise ValueError(f"unsupported debug protocol: {protocol}; supported: litetune")
    if transport not in {"uart", "usb-cdc"}:
        raise ValueError(f"unsupported LiteTune transport: {transport}; supported: uart, usb-cdc")

    src = transport_template_source()
    dst = Path(output)
    if not dst.is_absolute():
        dst = framework_root() / dst

    if not src.exists():
        raise FileNotFoundError(f"transport template not found: {src}")
    if dst.exists() and not force:
        raise FileExistsError(f"output already exists: {dst}; pass --force to overwrite")

    dst.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8")
    content = content.replace("EFW + LiteTune debug.", f"EFW + LiteTune debug over {transport}.")
    dst.write_text(content, encoding="utf-8")
    return TransportTemplateResult(source=src, output=dst, protocol=protocol, transport=transport, created=True)
