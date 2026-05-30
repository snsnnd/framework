"""Board profile and pin-planner helpers for EFW Studio."""

from __future__ import annotations

from typing import Any


def apply_board_profile_defaults_to_graph(graph: dict[str, Any], board_profiles: dict[str, dict[str, Any]], profile_name: str) -> list[str]:
    """Apply safe profile defaults to graph pins and return human-readable notes."""
    profile = board_profiles.get(profile_name) or board_profiles.get("generic-mock") or {}
    ports = list(profile.get("ports", ["A"])) or ["A"]
    pins_per_port = int(profile.get("pins_per_port", 16) or 16)
    timers = list(profile.get("timers", [1])) or [1]
    pwm_channels = list(profile.get("pwm_channels", [1])) or [1]
    graph.setdefault("board", {})["profile"] = profile_name
    notes: list[str] = [f"Board Profile: {profile_name}"]
    gpio_index = 0
    motor_index = 0
    pin_plan: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if node.get("type") == "hal.gpio_line_input":
            channels = int(node.get("channels", len(node.get("pins", [])) or 5))
            pins = []
            for channel in range(channels):
                port = ports[(gpio_index // pins_per_port) % len(ports)]
                pin = gpio_index % pins_per_port
                pins.append({"port": str(port), "pin": int(pin)})
                pin_plan.append({"node": node.get("id"), "usage": f"GPIO输入[{channel}]", "port": str(port), "pin": int(pin)})
                gpio_index += 1
            node["pins"] = pins
            node["channels"] = channels
            notes.append(f"{node.get('id')}: 分配 {channels} 路 GPIO 输入")
        elif node.get("type") == "actuator.motor":
            timer = int(timers[motor_index % len(timers)])
            channel = int(pwm_channels[motor_index % len(pwm_channels)])
            dir_port = ports[(gpio_index // pins_per_port) % len(ports)]
            dir_pin = gpio_index % pins_per_port
            node["pwm"] = {"timer": timer, "channel": channel}
            node["dir_pin"] = {"port": str(dir_port), "pin": int(dir_pin)}
            pin_plan.append({"node": node.get("id"), "usage": "PWM", "timer": timer, "channel": channel})
            pin_plan.append({"node": node.get("id"), "usage": "DIR", "port": str(dir_port), "pin": int(dir_pin)})
            gpio_index += 1
            motor_index += 1
            notes.append(f"{node.get('id')}: 分配 TIM{timer}/CH{channel} + DIR {dir_port}{dir_pin}")
    graph.setdefault("board", {})["pin_plan"] = pin_plan
    return notes
