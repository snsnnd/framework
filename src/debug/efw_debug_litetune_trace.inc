typedef struct {
    char text[EFW_DEBUG_LITETUNE_TRACE_TEXT_SIZE];
    uint16_t event_id;
    uint16_t name_id;
    int32_t status;
    uint32_t mcu_time_ms;
    uint32_t duration_ms;
} efw_debug_litetune_trace_record_t;

static efw_debug_litetune_trace_record_t g_trace_queue[EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE];
static uint8_t g_trace_head;
static uint8_t g_trace_tail;
static uint8_t g_trace_count;
static efw_debug_litetune_perf_t g_litetune_perf;
static uint16_t g_trace_event_id;
static uint16_t g_trace_name_id;
static int32_t g_trace_status;
static uint32_t g_trace_mcu_time_ms;
static uint32_t g_trace_duration_ms;

static const lt_log_field_desc_t g_trace_fields[] = {
    { EFW_DEBUG_LITETUNE_TRACE_EVENT_FIELD_ID, (uint8_t)LT_VALUE_U16, "trace.event_id", "", &g_trace_event_id },
    { EFW_DEBUG_LITETUNE_TRACE_NAME_FIELD_ID, (uint8_t)LT_VALUE_U16, "trace.name_id", "", &g_trace_name_id },
    { EFW_DEBUG_LITETUNE_TRACE_STATUS_FIELD_ID, (uint8_t)LT_VALUE_I32, "trace.status", "", &g_trace_status },
    { EFW_DEBUG_LITETUNE_TRACE_TIME_FIELD_ID, (uint8_t)LT_VALUE_U32, "trace.mcu_time_ms", "ms", &g_trace_mcu_time_ms },
    { EFW_DEBUG_LITETUNE_TRACE_DURATION_FIELD_ID, (uint8_t)LT_VALUE_U32, "trace.duration_ms", "ms", &g_trace_duration_ms },
};

static uint8_t bounded_cstr_len_u8(const char *text)
{
    uint8_t len = 0u;
    if (!text) {
        return 0u;
    }
    while (len < 255u && text[len] != '\0') {
        len++;
    }
    return len;
}

static uint16_t trace_dict_id(const char *text)
{
    uint32_t hash = 2166136261u;
    const unsigned char *cursor = (const unsigned char *)(text ? text : "");
    while (*cursor) {
        hash ^= (uint32_t)(*cursor++);
        hash *= 16777619u;
    }
    hash ^= (hash >> 16);
    return (uint16_t)(hash & 0xFFFFu);
}

static void parse_trace_detail(const char *detail, int32_t *status, uint32_t *mcu_time_ms, uint32_t *duration_ms)
{
    long parsed_status = 0;
    unsigned long parsed_time = 0ul;
    unsigned long parsed_duration = 0xFFFFFFFFul;
    const char *cursor;

    if (status) {
        *status = 0;
    }
    if (mcu_time_ms) {
        *mcu_time_ms = 0u;
    }
    if (duration_ms) {
        *duration_ms = 0xFFFFFFFFu;
    }
    if (!detail) {
        return;
    }
    cursor = strstr(detail, "status=");
    if (cursor) {
        (void)sscanf(cursor, "status=%ld", &parsed_status);
    }
    cursor = strstr(detail, "mcu_time_ms=");
    if (cursor) {
        (void)sscanf(cursor, "mcu_time_ms=%lu", &parsed_time);
    }
    cursor = strstr(detail, "duration_ms=");
    if (cursor && strstr(cursor, "duration_ms=unknown") != cursor) {
        (void)sscanf(cursor, "duration_ms=%lu", &parsed_duration);
    }
    if (status) {
        *status = (int32_t)parsed_status;
    }
    if (mcu_time_ms) {
        *mcu_time_ms = (uint32_t)parsed_time;
    }
    if (duration_ms) {
        *duration_ms = (uint32_t)parsed_duration;
    }
}

static void trace_queue_reset(void)
{
    g_trace_head = 0u;
    g_trace_tail = 0u;
    g_trace_count = 0u;
    (void)memset(&g_litetune_perf, 0, sizeof(g_litetune_perf));
}

static void trace_queue_push(const char *event, const char *name, const char *detail, const char *text)
{
    efw_debug_litetune_trace_record_t *record;
    g_litetune_perf.events_received++;
    if (!text) {
        g_litetune_perf.events_dropped++;
        return;
    }
    if (g_trace_count >= (uint8_t)EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE) {
        g_litetune_perf.events_dropped++;
        return;
    }
    record = &g_trace_queue[g_trace_tail];
    snprintf(record->text, EFW_DEBUG_LITETUNE_TRACE_TEXT_SIZE, "%s", text);
    record->event_id = trace_dict_id(event);
    record->name_id = trace_dict_id(name);
    parse_trace_detail(detail, &record->status, &record->mcu_time_ms, &record->duration_ms);
    g_trace_tail = (uint8_t)((g_trace_tail + 1u) % (uint8_t)EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE);
    g_trace_count++;
    g_litetune_perf.events_queued++;
    g_litetune_perf.current_queue_depth = g_trace_count;
    if (g_litetune_perf.max_queue_depth < g_trace_count) {
        g_litetune_perf.max_queue_depth = g_trace_count;
    }
}

static uint8_t trace_queue_pop(efw_debug_litetune_trace_record_t *out)
{
    if (!out || g_trace_count == 0u) {
        return 0u;
    }
    *out = g_trace_queue[g_trace_head];
    g_trace_head = (uint8_t)((g_trace_head + 1u) % (uint8_t)EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE);
    g_trace_count--;
    g_litetune_perf.current_queue_depth = g_trace_count;
    return 1u;
}

static void litetune_debug_event_sink(const char *event, const char *name, const char *detail, void *user)
{
    char text[EFW_DEBUG_LITETUNE_TRACE_TEXT_SIZE];
    (void)user;
    if (!g_litetune_ready) {
        return;
    }
    snprintf(text, sizeof(text), "%s name=%s %s", event ? event : "event", name ? name : "", detail ? detail : "");
    trace_queue_push(event, name, detail, text);
}
