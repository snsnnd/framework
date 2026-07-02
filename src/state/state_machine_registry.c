#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/state/state_machine.h"

#if EFW_ENABLE_STATE_MACHINE

static efw_sm_context_t *g_sm_pool[EFW_MAX_STATE_MACHINES];
static size_t g_sm_n;

static efw_status_t sm_enter(efw_sm_context_t *ctx) {
    if (!ctx || !ctx->current) return EFW_OK;
    if (ctx->current->on_enter) {
        efw_status_t s = ctx->current->on_enter(ctx->current->ctx);
        if (s != EFW_OK) return s;
    }
    ctx->entered_ms = ctx->elapsed_ms;
    return EFW_OK;
}

static efw_status_t sm_exit(efw_sm_context_t *ctx) {
    if (!ctx || !ctx->current) return EFW_OK;
    if (ctx->current->on_exit) {
        return ctx->current->on_exit(ctx->current->ctx);
    }
    return EFW_OK;
}

static int sm_eval_transition(const efw_sm_transition_t *t, const efw_sm_context_t *ctx, uint32_t time_in_state) {
    if (t->from && t->from != ctx->current) return 0;
    if (t->timeout_ms > 0 && time_in_state >= t->timeout_ms) return 1;
    if (t->condition && t->condition()) return 1;
    return 0;
}

efw_status_t efw_sm_registry_init(void) {
    g_sm_n = 0;
    for (size_t i = 0; i < EFW_MAX_STATE_MACHINES; ++i) {
        g_sm_pool[i] = 0;
    }
    return EFW_OK;
}

efw_status_t efw_sm_register(efw_sm_context_t *ctx) {
    if (!ctx || !ctx->name) {
        efw_diag_set(EFW_ERR_INVALID, "sm", 0, "invalid context");
        return EFW_ERR_INVALID;
    }
    for (size_t i = 0; i < g_sm_n; ++i) {
        if (g_sm_pool[i] && efw_name_eq(g_sm_pool[i]->name, ctx->name)) {
            efw_diag_set(EFW_ERR_ALREADY_EXISTS, "sm", ctx->name, "duplicate name");
            return EFW_ERR_ALREADY_EXISTS;
        }
    }
    if (g_sm_n >= EFW_MAX_STATE_MACHINES) {
        efw_diag_set(EFW_ERR_FULL, "sm", ctx->name, "pool full");
        return EFW_ERR_FULL;
    }
    g_sm_pool[g_sm_n++] = ctx;
    return EFW_OK;
}

efw_status_t efw_sm_get(const char *name, efw_sm_context_t **out_ctx) {
    for (size_t i = 0; i < g_sm_n; ++i) {
        if (g_sm_pool[i] && efw_name_eq(g_sm_pool[i]->name, name)) {
            if (out_ctx) *out_ctx = g_sm_pool[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_sm_unregister(const char *name) {
    for (size_t i = 0; i < g_sm_n; ++i) {
        if (g_sm_pool[i] && efw_name_eq(g_sm_pool[i]->name, name)) {
            g_sm_pool[i] = g_sm_pool[--g_sm_n];
            g_sm_pool[g_sm_n] = 0;
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_sm_count(void) { return g_sm_n; }

efw_status_t efw_sm_init(efw_sm_context_t *ctx, const char *name,
                          const efw_state_def_t *initial,
                          const efw_sm_transition_t *transitions, uint8_t count) {
    if (!ctx || !initial) return EFW_ERR_INVALID;
    ctx->name = name;
    ctx->current = initial;
    ctx->transitions = transitions;
    ctx->transition_count = count;
    ctx->elapsed_ms = 0;
    ctx->entered_ms = 0;
    return sm_enter(ctx);
}

efw_status_t efw_sm_transition_to(efw_sm_context_t *ctx, const efw_state_def_t *target) {
    if (!ctx || !target) return EFW_ERR_INVALID;
    if (ctx->current == target) return EFW_OK;
    efw_status_t s = sm_exit(ctx);
    if (s != EFW_OK) return s;
    ctx->current = target;
    return sm_enter(ctx);
}

efw_status_t efw_sm_tick(efw_sm_context_t *ctx) {
    if (!ctx || !ctx->current) return EFW_ERR_INVALID;
    const efw_state_def_t *state_at_entry = ctx->current;
    uint32_t entered_at = ctx->entered_ms;
    efw_status_t s = EFW_OK;
    if (ctx->current->on_tick) {
        s = ctx->current->on_tick(ctx->current->ctx);
        if (s != EFW_OK) return s;
    }
    if (ctx->current != state_at_entry) return EFW_OK;
    if (!ctx->transitions || ctx->transition_count == 0) return EFW_OK;
    uint32_t time_in_state = ctx->elapsed_ms - entered_at;
    int best_idx = -1;
    uint8_t best_prio = 0;
    for (uint8_t i = 0; i < ctx->transition_count; ++i) {
        const efw_sm_transition_t *t = &ctx->transitions[i];
        if (t->priority < best_prio) continue;
        if (!sm_eval_transition(t, ctx, time_in_state)) continue;
        best_idx = (int)i;
        best_prio = t->priority;
    }
    if (best_idx >= 0) {
        const efw_sm_transition_t *t = &ctx->transitions[best_idx];
        if (t->action) {
            s = t->action();
            if (s != EFW_OK) return s;
        }
        return efw_sm_transition_to(ctx, t->to);
    }
    return EFW_OK;
}

const char *efw_sm_current_state(const efw_sm_context_t *ctx) {
    if (!ctx || !ctx->current) return "";
    return ctx->current->name;
}

const efw_state_def_t *efw_sm_current_def(const efw_sm_context_t *ctx) {
    if (!ctx) return 0;
    return ctx->current;
}

uint32_t efw_sm_time_in_state(const efw_sm_context_t *ctx) {
    if (!ctx) return 0;
    return ctx->elapsed_ms - ctx->entered_ms;
}

void efw_sm_set_elapsed(efw_sm_context_t *ctx, uint32_t elapsed_ms) {
    if (ctx) ctx->elapsed_ms = elapsed_ms;
}

efw_status_t efw_sm_set_transitions(efw_sm_context_t *ctx, const efw_sm_transition_t *transitions, uint8_t count) {
    if (!ctx) return EFW_ERR_INVALID;
    ctx->transitions = transitions;
    ctx->transition_count = count;
    return EFW_OK;
}

#endif
