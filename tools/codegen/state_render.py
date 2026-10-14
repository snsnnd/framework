"""State-machine and project-module C render helpers."""

from __future__ import annotations

try:
    from .utils import c_ident, c_str
except ImportError:  # pragma: no cover
    from codegen.utils import c_ident, c_str


def render_project_module_shells(module_runtime_model):
    parts = []
    for module_runtime in module_runtime_model:
        node = module_runtime["node"]
        ident = module_runtime["ident"]
        parts.append(f"static efw_status_t app_project_module_{ident}_poll(void *ctx) {{\n    efw_status_t s;\n    EFW_UNUSED(ctx);\n")
        for publisher in module_runtime["publishers"]:
            parts.append(f"    s = app_publish_{publisher['ident']}_auto();\n    if (s != EFW_OK) return s;\n")
        for machine in module_runtime["state_machines"]:
            parts.append(f"    s = app_sm_{machine['ident']}_tick();\n    if (s != EFW_OK) return s;\n")
        parts.append("    return EFW_OK;\n}\n\n")
        parts.append(f"""static efw_module_ops_t g_{ident}_project_module = {{
    .name = {c_str(node['id'])},
    .type = EFW_MODULE_APP,
    .ctx = 0,
    .poll = app_project_module_{ident}_poll,
}};

""")
    return "".join(parts)


def render_project_module_registrations(module_runtime_model):
    return "".join(
        f"    s = efw_module_register(&g_{item['ident']}_project_module);\n    if (s != EFW_OK) return s;\n"
        for item in module_runtime_model
    )


def render_state_api_declarations(state_runtime_model):
    lines = []
    for machine_runtime in state_runtime_model:
        ident = machine_runtime["ident"]
        lines.append(f"efw_status_t app_sm_{ident}_tick(void);\n")
        lines.append(f"efw_status_t app_sm_{ident}_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);\n")
        lines.append(f"efw_status_t app_sm_{ident}_transition_to(const char *state_name);\n")
        lines.append(f"const char *app_sm_{ident}_current_state(void);\n")
    return "".join(lines)


def render_state_machine_bundle(machine_runtime):
    parts = []
    m_ident = machine_runtime["ident"]
    states = machine_runtime["states"]
    state_symbols = {state["id"]: f"g_{m_ident}_state_{c_ident(state['id'])}" for state in states}
    for state in states:
        symbol = state_symbols[state["id"]]
        parts.append(f"static const efw_state_def_t {symbol} = {{\n")
        parts.append(f"    .name = {c_str(state['id'])},\n    .ctx = 0,\n")
        parts.append(f"    .on_enter = {c_ident(state['on_enter']) if state.get('on_enter') else '0'},\n")
        parts.append(f"    .on_tick = {c_ident(state['on_update']) if state.get('on_update') else 'app_noop_status'},\n")
        parts.append(f"    .on_exit = {c_ident(state['on_exit']) if state.get('on_exit') else '0'},\n}};\n")
    initial = machine_runtime["machine"].get("initial") or (states[0]["id"] if states else "")
    normal_transitions = [item for item in machine_runtime["transitions"] if not str(item.get("event_trigger", "")).strip()]
    if normal_transitions:
        parts.append(f"static const efw_sm_transition_t g_{m_ident}_transitions[] = {{\n")
        for transition in normal_transitions:
            parts.append("    {\n")
            parts.append(f"        .from = &{state_symbols[transition['from']]},\n")
            parts.append(f"        .to = &{state_symbols[transition['to']]},\n")
            parts.append(f"        .condition = {c_ident(transition['condition'])},\n")
            parts.append(f"        .action = {c_ident(transition['action']) if transition.get('action') else '0'},\n")
            parts.append(f"        .timeout_ms = {int(transition.get('timeout_ms', 0))}u,\n")
            parts.append(f"        .priority = {int(transition.get('priority', 0))}u,\n")
            parts.append("    },\n")
        parts.append("};\n")
    parts.append(f"static efw_sm_context_t g_{m_ident}_sm;\n")
    parts.append(f"static efw_status_t app_{m_ident}_register(void) {{\n    efw_status_t s;\n")
    if states:
        transitions_expr = f"g_{m_ident}_transitions" if normal_transitions else "0"
        parts.append(f"    s = efw_sm_init(&g_{m_ident}_sm, {c_str(machine_runtime['machine_id'])}, &{state_symbols[initial]}, {transitions_expr}, {len(normal_transitions)}u);\n")
        parts.append("    if (s != EFW_OK) return s;\n")
        parts.append(f"    return efw_sm_register(&g_{m_ident}_sm);\n")
    else:
        parts.append("    EFW_UNUSED(s);\n    return EFW_ERR_INVALID;\n")
    parts.append("}\n")
    parts.append(f"const char *app_sm_{m_ident}_current_state(void) {{\n    return efw_sm_current_state(&g_{m_ident}_sm);\n}}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_transition_to(const char *state_name) {{\n")
    for state in states:
        parts.append(f"    if (app_bootstrap_name_eq(state_name, {c_str(state['id'])})) return efw_sm_transition_to(&g_{m_ident}_sm, &{state_symbols[state['id']]});\n")
    parts.append("    return EFW_ERR_NOT_FOUND;\n}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size) {{\n    EFW_UNUSED(data);\n    EFW_UNUSED(size);\n")
    eventful_transitions = [item for item in machine_runtime["transitions"] if str(item.get("event_trigger", "")).strip()]
    if not eventful_transitions:
        parts.append("    EFW_UNUSED(event_name);\n    EFW_UNUSED(topic_id);\n")
    if states:
        ordered_transitions = [
            item
            for _index, item in sorted(
                enumerate(machine_runtime["transitions"]),
                key=lambda pair: (int(pair[1].get("priority", 0)), pair[0]),
                reverse=True,
            )
        ]
        eventful = [transition for transition in ordered_transitions if str(transition.get("event_trigger", "")).strip()]
        for transition in eventful:
            cond = c_ident(transition["condition"]) + "()"
            parts.append(f"    if (efw_sm_current_def(&g_{m_ident}_sm) == &{state_symbols[transition['from']]} && app_bootstrap_event_matches({c_str(transition.get('event_trigger'))}, event_name, topic_id) && ({cond})) {{\n")
            if transition.get("action"):
                parts.append(f"        efw_status_t s = {c_ident(transition['action'])}();\n        if (s != EFW_OK) return s;\n")
            parts.append(f"        return efw_sm_transition_to(&g_{m_ident}_sm, &{state_symbols[transition['to']]});\n    }}\n")
    parts.append("    return EFW_ERR_NOT_FOUND;\n}\n")
    parts.append(f"efw_status_t app_sm_{m_ident}_tick(void) {{\n    efw_sm_set_elapsed(&g_{m_ident}_sm, app_elapsed_ms());\n    return efw_sm_tick(&g_{m_ident}_sm);\n}}\n\n")
    return "".join(parts)
