static lt_param_desc_t g_litetune_params[EFW_MAX_DEBUG_POINTS];
static lt_log_field_desc_t g_litetune_fields[EFW_MAX_DEBUG_POINTS];
static const void *g_litetune_string_sources[EFW_MAX_DEBUG_POINTS];
static lt_str8_view_t g_litetune_string_views[EFW_MAX_DEBUG_POINTS];
static lt_param_registry_t g_litetune_param_registry;
static lt_log_layout_desc_t g_litetune_layouts[2];
static lt_log_registry_t g_litetune_log_registry;

static void refresh_string_views(void)
{
    uint16_t i;
    for (i = 0u; i < g_litetune_param_count; ++i) {
        const char *text = (const char *)g_litetune_string_sources[i];
        if (!text) {
            continue;
        }
        g_litetune_string_views[i].data = (const uint8_t *)text;
        g_litetune_string_views[i].len = bounded_cstr_len_u8(text);
    }
}

static uint8_t map_debug_type_to_litetune(efw_debug_type_t debug_type)
{
    switch (debug_type) {
    case EFW_DEBUG_TYPE_BOOL:
        return (uint8_t)LT_VALUE_BOOL;
    case EFW_DEBUG_TYPE_U8:
        return (uint8_t)LT_VALUE_U8;
    case EFW_DEBUG_TYPE_I8:
        return (uint8_t)LT_VALUE_I8;
    case EFW_DEBUG_TYPE_U16:
        return (uint8_t)LT_VALUE_U16;
    case EFW_DEBUG_TYPE_I16:
        return (uint8_t)LT_VALUE_I16;
    case EFW_DEBUG_TYPE_U32:
        return (uint8_t)LT_VALUE_U32;
    case EFW_DEBUG_TYPE_I32:
        return (uint8_t)LT_VALUE_I32;
    case EFW_DEBUG_TYPE_F32:
        return (uint8_t)LT_VALUE_F32;
    case EFW_DEBUG_TYPE_F64:
        return (uint8_t)LT_VALUE_F64;
    case EFW_DEBUG_TYPE_STRING:
        return (uint8_t)LT_VALUE_STRING;
    default:
        return (uint8_t)LT_VALUE_INVALID;
    }
}

static uint8_t get_debug_type_size(efw_debug_type_t type)
{
    switch (type) {
    case EFW_DEBUG_TYPE_BOOL:
    case EFW_DEBUG_TYPE_U8:
    case EFW_DEBUG_TYPE_I8:
        return 1u;
    case EFW_DEBUG_TYPE_U16:
    case EFW_DEBUG_TYPE_I16:
        return 2u;
    case EFW_DEBUG_TYPE_U32:
    case EFW_DEBUG_TYPE_I32:
    case EFW_DEBUG_TYPE_F32:
        return 4u;
    case EFW_DEBUG_TYPE_F64:
        return 8u;
    case EFW_DEBUG_TYPE_STRING:
        return (uint8_t)sizeof(lt_str8_view_t);
    default:
        return 0u;
    }
}

static void build_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    uint16_t *count = (uint16_t *)user;
    uint8_t value_type;

    if (!point || !point->registered || !point->value_ptr || !count || *count >= (uint16_t)EFW_MAX_DEBUG_POINTS) {
        return;
    }

    value_type = map_debug_type_to_litetune(point->type);
    if (value_type == (uint8_t)LT_VALUE_INVALID) {
        return;
    }

    if (value_type == (uint8_t)LT_VALUE_STRING) {
        g_litetune_string_sources[*count] = point->value_ptr;
        g_litetune_string_views[*count].data = (const uint8_t *)point->value_ptr;
        g_litetune_string_views[*count].len = bounded_cstr_len_u8((const char *)point->value_ptr);
    }

    g_litetune_params[*count].param_id = (lt_param_id_t)point->param_id;
    g_litetune_params[*count].value_type = value_type;
    g_litetune_params[*count].name = point->name;
    g_litetune_params[*count].unit = "";
    g_litetune_params[*count].value_ptr = (value_type == (uint8_t)LT_VALUE_STRING) ? (void *)&g_litetune_string_views[*count] : (void *)point->value_ptr;
    g_litetune_params[*count].flags = LT_PARAM_FLAG_READABLE;
    g_litetune_params[*count].min_value_ptr = 0;
    g_litetune_params[*count].max_value_ptr = 0;
    g_litetune_params[*count].default_value_ptr = 0;

    g_litetune_fields[*count].field_id = (lt_field_id_t)point->param_id;
    g_litetune_fields[*count].value_type = value_type;
    g_litetune_fields[*count].name = point->name;
    g_litetune_fields[*count].unit = "";
    g_litetune_fields[*count].value_ptr = (value_type == (uint8_t)LT_VALUE_STRING) ? (const void *)&g_litetune_string_views[*count] : point->value_ptr;

    *count = (uint16_t)(*count + 1u);
}

static efw_status_t build_litetune_registries(uint16_t telemetry_period_ms)
{
    g_litetune_param_count = 0u;
    (void)memset(g_litetune_params, 0, sizeof(g_litetune_params));
    (void)memset(g_litetune_fields, 0, sizeof(g_litetune_fields));
    (void)memset(g_litetune_string_sources, 0, sizeof(g_litetune_string_sources));
    (void)memset(g_litetune_string_views, 0, sizeof(g_litetune_string_views));
    efw_debug_foreach_point(build_litetune_point_iter, &g_litetune_param_count);
    refresh_string_views();

    g_litetune_param_registry.param_count = g_litetune_param_count;
    g_litetune_param_registry.params = g_litetune_params;

    g_litetune_layouts[0].layout_id = EFW_DEBUG_LITETUNE_LAYOUT_DEBUG;
    g_litetune_layouts[0].default_period_ms = telemetry_period_ms ? telemetry_period_ms : 100u;
    g_litetune_layouts[0].field_count = (uint8_t)((g_litetune_param_count > 255u) ? 255u : g_litetune_param_count);
    g_litetune_layouts[0].fields = g_litetune_fields;

    g_litetune_layouts[1].layout_id = EFW_DEBUG_LITETUNE_LAYOUT_TRACE;
    g_litetune_layouts[1].default_period_ms = 0u;
    g_litetune_layouts[1].field_count = (uint8_t)(sizeof(g_trace_fields) / sizeof(g_trace_fields[0]));
    g_litetune_layouts[1].fields = g_trace_fields;

    g_litetune_log_registry.layout_count = 2u;
    g_litetune_log_registry.layouts = g_litetune_layouts;

    return EFW_OK;
}

static efw_status_t register_point_to_litetune(const efw_debug_point_t *point)
{
    if (!point || !point->registered) {
        return EFW_ERR_INVALID;
    }
    return EFW_OK;
}

static efw_status_t update_litetune_param(const efw_debug_point_t *point)
{
    if (!point || !point->registered || !point->value_ptr) {
        return EFW_ERR_INVALID;
    }
    return EFW_OK;
}

static void register_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    int *count = (int *)user;
    if (count && register_point_to_litetune(point) == EFW_OK) {
        (*count)++;
    }
}

static void sync_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    int *count = (int *)user;
    if (count && update_litetune_param(point) == EFW_OK) {
        (*count)++;
    }
}
