/**
 * @file    efw_debug_litetune.c
 * @brief   EFW 调试模块与 LiteTune 协议的集成层
 *
 * 本文件实现将 EFW 调试监控点映射为 LiteTune 协议参数的功能。
 * 需要 LiteTune MCU 库支持。
 */

#include "efw/debug/efw_debug.h"
#include <string.h>

/* LiteTune 头文件 - 根据实际项目路径调整 */
/* #include "litetune/include/lt_params.h" */
/* #include "litetune/include/lt_registry.h" */

/* ==================================================================
 *  LiteTune 参数类型映射
 * ================================================================== */

/**
 * @brief 将 EFW 调试类型映射为 LiteTune 值类型
 *
 * @param debug_type EFW 调试类型
 * @return LiteTune 值类型 ID，0 表示未知类型
 */
static uint8_t map_debug_type_to_litetune(efw_debug_type_t debug_type)
{
    /* LiteTune 值类型定义（来自 litetune_protocol.py）：
     * 0x01: bool
     * 0x02: u8
     * 0x03: i8
     * 0x04: u16
     * 0x05: i16
     * 0x06: u32
     * 0x07: i32
     * 0x08: u64
     * 0x09: i64
     * 0x0A: f32
     * 0x0B: f64
     * 0x0C: string
     * 0x0D: bytes
     */

    switch (debug_type) {
        case EFW_DEBUG_TYPE_BOOL:   return 0x01;
        case EFW_DEBUG_TYPE_U8:     return 0x02;
        case EFW_DEBUG_TYPE_I8:     return 0x03;
        case EFW_DEBUG_TYPE_U16:    return 0x04;
        case EFW_DEBUG_TYPE_I16:    return 0x05;
        case EFW_DEBUG_TYPE_U32:    return 0x06;
        case EFW_DEBUG_TYPE_I32:    return 0x07;
        case EFW_DEBUG_TYPE_F32:    return 0x0A;
        case EFW_DEBUG_TYPE_F64:    return 0x0B;
        case EFW_DEBUG_TYPE_STRING: return 0x0C;
        default:                    return 0x00;
    }
}

/**
 * @brief 获取调试类型的字节大小
 */
static uint8_t get_debug_type_size(efw_debug_type_t type)
{
    switch (type) {
        case EFW_DEBUG_TYPE_BOOL:   return 1;
        case EFW_DEBUG_TYPE_U8:
        case EFW_DEBUG_TYPE_I8:     return 1;
        case EFW_DEBUG_TYPE_U16:
        case EFW_DEBUG_TYPE_I16:    return 2;
        case EFW_DEBUG_TYPE_U32:
        case EFW_DEBUG_TYPE_I32:
        case EFW_DEBUG_TYPE_F32:    return 4;
        case EFW_DEBUG_TYPE_F64:    return 8;
        default:                    return 0;
    }
}

/* ==================================================================
 *  LiteTune 参数注册
 * ================================================================== */

/**
 * @brief 注册单个调试监控点到 LiteTune 参数表
 *
 * @param point 调试监控点
 * @return EFW_OK 成功，其他值表示失败
 */
static efw_status_t register_point_to_litetune(const efw_debug_point_t *point)
{
    if (!point || !point->registered) {
        return EFW_ERR_INVALID;
    }

    /* LiteTune 参数注册接口（需要根据实际 API 调整）
     *
     * 示例：
     * lt_param_desc_t desc = {
     *     .id = point->param_id,
     *     .type = map_debug_type_to_litetune(point->type),
     *     .name = point->name,
     *     .unit = "",  // 调试参数通常无单位
     * };
     * return lt_register_param(&desc);
     */

    (void)point;  /* 避免未使用警告 */
    return EFW_OK;
}

/**
 * @brief 更新 LiteTune 参数值
 *
 * @param point 调试监控点
 * @return EFW_OK 成功，其他值表示失败
 */
static efw_status_t update_litetune_param(const efw_debug_point_t *point)
{
    if (!point || !point->registered || !point->value_ptr) {
        return EFW_ERR_INVALID;
    }

    /* LiteTune 参数值更新接口（需要根据实际 API 调整）
     *
     * 示例：
     * return lt_param_set_value(point->param_id, point->value_ptr,
     *                          get_debug_type_size(point->type));
     */

    (void)point;  /* 避免未使用警告 */
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

/* ==================================================================
 *  批量操作
 * ================================================================== */

/**
 * @brief 注册所有调试监控点到 LiteTune
 *
 * 此函数应在 efw_debug_init() 之后、efw_debug_update() 之前调用。
 *
 * @return 成功注册的数量，负值表示错误
 */
int efw_debug_litetune_register_all(void)
{
    int registered = 0;
    efw_debug_foreach_point(register_litetune_point_iter, &registered);
    return registered;
}

/**
 * @brief 同步所有调试监控点值到 LiteTune
 *
 * 此函数在 efw_debug_update() 内部调用。
 *
 * @return 成功同步的数量，负值表示错误
 */
int efw_debug_litetune_sync_all(void)
{
    int synced = 0;
    efw_debug_foreach_point(sync_litetune_point_iter, &synced);
    return synced;
}

typedef struct {
    uint8_t *response;
    uint16_t response_size;
    uint16_t offset;
} efw_debug_list_writer_t;

typedef struct {
    uint8_t *buffer;
    uint16_t buffer_size;
    uint16_t offset;
} efw_debug_snapshot_writer_t;

static void write_debug_list_item(const efw_debug_point_t *point, void *user)
{
    efw_debug_list_writer_t *writer = (efw_debug_list_writer_t *)user;
    if (!point || !writer || writer->offset >= writer->response_size) {
        return;
    }

    uint8_t name_len = (uint8_t)strlen(point->name);
    if ((uint16_t)(writer->offset + 1u + name_len + 3u) > writer->response_size) {
        return;
    }

    writer->response[writer->offset++] = name_len;
    memcpy(&writer->response[writer->offset], point->name, name_len);
    writer->offset = (uint16_t)(writer->offset + name_len);
    writer->response[writer->offset++] = (uint8_t)point->type;
    writer->response[writer->offset++] = (uint8_t)(point->param_id & 0xFFu);
    writer->response[writer->offset++] = (uint8_t)((point->param_id >> 8) & 0xFFu);
}

static void write_debug_snapshot_item(const efw_debug_point_t *point, void *user)
{
    efw_debug_snapshot_writer_t *writer = (efw_debug_snapshot_writer_t *)user;
    if (!point || !writer || !point->value_ptr) {
        return;
    }

    uint8_t value_size = get_debug_type_size(point->type);
    if (value_size == 0 || (uint16_t)(writer->offset + 3u + value_size) > writer->buffer_size) {
        return;
    }

    writer->buffer[writer->offset++] = (uint8_t)(point->param_id & 0xFFu);
    writer->buffer[writer->offset++] = (uint8_t)((point->param_id >> 8) & 0xFFu);
    writer->buffer[writer->offset++] = value_size;
    memcpy(&writer->buffer[writer->offset], point->value_ptr, value_size);
    writer->offset = (uint16_t)(writer->offset + value_size);
}

/* ==================================================================
 *  LiteTune 命令处理
 * ================================================================== */

/**
 * @brief 处理来自 Host 的调试命令
 *
 * 支持的命令：
 *   - debug.list    : 列出所有监控点
 *   - debug.get     : 获取指定监控点值
 *   - debug.stats   : 获取调试模块统计信息
 *
 * @param cmd_name 命令名称
 * @param payload  命令负载
 * @param payload_len 负载长度
 * @param response 响应缓冲区
 * @param response_size 响应缓冲区大小
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_handle_command(const char *cmd_name,
                                       const uint8_t *payload, uint16_t payload_len,
                                       uint8_t *response, uint16_t response_size)
{
    if (!cmd_name || !response) {
        return EFW_ERR_INVALID;
    }

    /* debug.list 命令 */
    if (strcmp(cmd_name, "debug.list") == 0) {
        /* 响应格式：[count(2B)] [name1, type1, param_id1] ... */
        uint16_t offset = 0;

        /* 写入监控点数量 */
        if (response_size < 2) {
            return EFW_ERR_RANGE;
        }
        uint16_t point_count = efw_debug_point_count();
        response[offset++] = (uint8_t)(point_count & 0xFFu);
        response[offset++] = (uint8_t)((point_count >> 8) & 0xFFu);

        efw_debug_list_writer_t writer = { response, response_size, offset };
        efw_debug_foreach_point(write_debug_list_item, &writer);

        return EFW_OK;
    }

    /* debug.stats 命令 */
    if (strcmp(cmd_name, "debug.stats") == 0) {
        efw_debug_stats_t stats;
        efw_status_t ret = efw_debug_get_stats(&stats);
        if (ret != EFW_OK) {
            return ret;
        }

        /* 响应格式：[total(2B)] [efw(2B)] [custom(2B)] [updates(4B)] [errors(4B)] */
        if (response_size < 14) {
            return EFW_ERR_RANGE;
        }

        uint16_t offset = 0;
        response[offset++] = (uint8_t)(stats.total_points & 0xFF);
        response[offset++] = (uint8_t)((stats.total_points >> 8) & 0xFF);
        response[offset++] = (uint8_t)(stats.efw_points & 0xFF);
        response[offset++] = (uint8_t)((stats.efw_points >> 8) & 0xFF);
        response[offset++] = (uint8_t)(stats.custom_points & 0xFF);
        response[offset++] = (uint8_t)((stats.custom_points >> 8) & 0xFF);

        /* 更新次数 */
        memcpy(&response[offset], &stats.update_count, 4);
        offset += 4;

        /* 错误次数 */
        memcpy(&response[offset], &stats.error_count, 4);
        offset += 4;

        return EFW_OK;
    }

    return EFW_ERR_UNSUPPORTED;
}

/* ==================================================================
 *  导出内部状态（供 Host 端读取）
 * ================================================================== */

/**
 * @brief 导出所有监控点的当前值到缓冲区
 *
 * 此函数用于批量读取所有监控点值，适用于遥测上报。
 *
 * @param buffer 输出缓冲区
 * @param buffer_size 缓冲区大小
 * @param out_len 实际写入长度
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_export_snapshot(uint8_t *buffer, uint16_t buffer_size,
                                        uint16_t *out_len)
{
    if (!buffer || !out_len) {
        return EFW_ERR_INVALID;
    }

    uint16_t offset = 0;

    /* 写入快照头：[timestamp(4B)] [count(2B)] */
    if (buffer_size < 6) {
        return EFW_ERR_RANGE;
    }

    efw_debug_stats_t stats;
    efw_status_t stats_ret = efw_debug_get_stats(&stats);
    if (stats_ret != EFW_OK) {
        return stats_ret;
    }

    /* 时间戳（简化为更新计数） */
    memcpy(&buffer[offset], &stats.update_count, 4);
    offset += 4;

    /* 监控点数量 */
    buffer[offset++] = (uint8_t)(stats.total_points & 0xFFu);
    buffer[offset++] = (uint8_t)((stats.total_points >> 8) & 0xFFu);

    efw_debug_snapshot_writer_t writer = { buffer, buffer_size, offset };
    efw_debug_foreach_point(write_debug_snapshot_item, &writer);
    offset = writer.offset;

    *out_len = offset;
    return EFW_OK;
}
