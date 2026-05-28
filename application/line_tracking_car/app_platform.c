/**
 * @file    app_platform.c
 * @brief   平台层实现 —— 注册所有硬件相关的组件 (ADC HAL / 传感器 / 电机执行器)
 *
 * 本文件是三层架构中的"平台层"实现。它负责：
 *   ① 定义硬件上下文结构体 (ADC 值存储、电机状态记录)
 *   ② 实现 HAL 和传感器回调函数 (ADC 读取、传感器读取、电机写入)
 *   ③ 填充并注册 HAL/SENSOR/ACTUATOR 的 ops 结构体
 *
 * =========================================================================
 * 硬件上下文
 * =========================================================================
 *
 *   app_line_input_ctx_t — 5 通道数字循迹状态容器
 *     真实项目中这里可以来自 GPIO、比较器输出，或 ADC 阈值化结果
 *     本示例中直接存储 5 个 0/1 值
 *
 *   app_motor_ctx_t — 电机状态记录器
 *     记录最后一次写入的速度和方向 (用于调试/日志)
 *     真实项目中这里应该存放 PWM 定时器句柄和 GPIO 引脚号
 *
 * =========================================================================
 * 注册的所有组件
 * =========================================================================
 *
 *   HAL:
 *     "line_input" (GPIO, bus_id=1) — 5 通道循迹数字输入
 *
 *   SENSOR:
 *     "line_sensor_5ch" (LINE_TRACKING, 5ch) — 绑定到 HAL "line_input"
 *
 *   ACTUATOR:
 *     "left_motor"  (MOTOR) — 左电机
 *     "right_motor" (MOTOR) — 右电机
 */

#include "app_platform.h"
#include "app_board_config.h"

/* ==================================================================
 *  硬件上下文结构体
 * ================================================================== */

/**
 * @brief 循迹 ADC 上下文 —— 存放 5 个模拟通道的值
 * 真实项目：替换为 ADC_HandleTypeDef* + DMA 缓冲区指针
 */
typedef struct {
    uint16_t channel[APP_LINE_CHANNELS]; /**< 5 个通道的模拟读数 */
    const app_gpio_pin_t *pins;
} app_line_input_ctx_t;

/**
 * @brief 电机上下文 —— 记录最后一次写入状态
 * 真实项目：替换为 TIM_HandleTypeDef* + GPIO 引脚号 + 方向引脚
 */
typedef struct {
    app_pwm_channel_t pwm;
    app_gpio_pin_t dir_pin;
    float last_speed;       /**< 最后一次速度指令 */
    float last_direction;   /**< 最后一次方向指令 */
} app_motor_ctx_t;

/* ==================================================================
 *  全局实例 (静态分配，无 malloc)
 * ================================================================== */

static app_line_input_ctx_t g_line_input = {
    .pins = APP_LINE_PINS,
};
static app_motor_ctx_t g_left_motor_ctx = {
    .pwm = APP_LEFT_MOTOR_PWM,
    .dir_pin = APP_LEFT_MOTOR_DIR,
};
static app_motor_ctx_t g_right_motor_ctx = {
    .pwm = APP_RIGHT_MOTOR_PWM,
    .dir_pin = APP_RIGHT_MOTOR_DIR,
};

/* ==================================================================
 *  回调函数实现
 * ================================================================== */

/**
 * @brief ADC HAL read 回调 —— 将 5 通道数据打包为 efw_line_tracking_data_t
 *
 * 从 ctx 的 channel[] 数组中逐通道复制到输出缓冲区。
 * 真实项目：从 ADC DMA 缓冲区读取，做必要的位运算/滤波处理
 *
 * @param ctx    指向 app_line_input_ctx_t 的指针
 * @param buf    输出缓冲区 (efw_line_tracking_data_t*)
 * @param len    期望长度 (应 ≥ sizeof(efw_line_tracking_data_t))
 * @param actual 输出参数：实际写入字节数
 */
static efw_status_t line_input_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    app_line_input_ctx_t *input = (app_line_input_ctx_t *)ctx;
    efw_line_tracking_data_t *out = (efw_line_tracking_data_t *)buf; /* buf → 输出结构体 */

    if (!input || !out || len < sizeof(efw_line_tracking_data_t)) return EFW_ERR_INVALID;

    out->count = APP_LINE_CHANNELS;                                 /* 设置通道数 = 5 */
    for (uint8_t i = 0; i < APP_LINE_CHANNELS; ++i) {
        out->value[i] = input->channel[i];                          /* 逐通道复制 0/1 状态 */
    }

    if (actual) *actual = sizeof(efw_line_tracking_data_t);         /* 告知实际写入大小 */
    return EFW_OK;
}

/**
 * @brief 循迹传感器 read 回调 —— 通过 HAL "line_input" 读取数据
 *
 * 传感器回调中调用 efw_hal_read() 访问底层 ADC。
 * 传感器不需要知道 ADC 在哪个引脚、什么配置——只需要 HAL 的名称。
 */
static efw_status_t line_sensor_read(void *ctx, void *out) {
    EFW_UNUSED(ctx);  /* 此传感器无私有上下文 */
    return efw_hal_read("line_input", out, sizeof(efw_line_tracking_data_t), 0);
}

/**
 * @brief 电机 write 回调 —— 接收速度和方向指令
 *
 * 真实项目：将 speed → PWM 占空比，direction → GPIO 方向引脚电平
 */
static efw_status_t motor_write(void *ctx, const void *cmd) {
    app_motor_ctx_t *motor = (app_motor_ctx_t *)ctx;                    /* ctx → 电机上下文 */
    const efw_motor_cmd_t *motor_cmd = (const efw_motor_cmd_t *)cmd;   /* cmd → 电机指令 */

    if (!motor || !motor_cmd) return EFW_ERR_INVALID;
    /* 真实项目在这里使用 motor->pwm 和 motor->dir_pin 调用芯片 SDK。 */
    motor->last_speed = motor_cmd->speed;          /* 记录速度 (调试用) */
    motor->last_direction = motor_cmd->direction;   /* 记录方向 (调试用) */
    return EFW_OK;
}

/* ==================================================================
 *  注册表条目 (静态定义的 ops 结构体)
 * ================================================================== */

/** 数字循迹输入 HAL — "line_input"，5 通道 */
static efw_hal_ops_t g_line_input_hal = {
    .name = "line_input",
    .type = EFW_HAL_GPIO,
    .bus_id = 1,
    .ctx = &g_line_input,
    .read = line_input_read,
};

/** 循迹传感器 — "line_sensor_5ch"，绑定 HAL "line_input" */
static efw_sensor_ops_t g_line_sensor = {
    .name = "line_sensor_5ch",
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = APP_LINE_CHANNELS, /* ★ 5 通道 */
    .hal_name = "line_input",
    .read = line_sensor_read,
};

/** 左电机执行器 — "left_motor" */
static efw_actuator_ops_t g_left_motor = {
    .name = "left_motor",
    .type = EFW_ACTUATOR_MOTOR,
    .ctx = &g_left_motor_ctx,
    .write = motor_write,
};

/** 右电机执行器 — "right_motor" */
static efw_actuator_ops_t g_right_motor = {
    .name = "right_motor",
    .type = EFW_ACTUATOR_MOTOR,
    .ctx = &g_right_motor_ctx,
    .write = motor_write,
};

/* ==================================================================
 *  平台注册函数
 * ================================================================== */

/**
 * @brief 注册平台层所有硬件组件
 *
 * 注册顺序是严格的：HAL → SENSOR → ACTUATOR
 * SENSOR 的 hal_name="line_input" 要求 HAL "line_input" 先注册。
 *
 * Fail-fast：任一步失败立即返回，不继续后续注册。
 */
efw_status_t app_platform_register(void) {
    efw_status_t s;

    s = efw_hal_register(&g_line_input_hal);
    if (s != EFW_OK) return s;
    s = efw_sensor_register(&g_line_sensor);      /* ② 注册传感器 (依赖 HAL) */
    if (s != EFW_OK) return s;
    s = efw_actuator_register(&g_left_motor);     /* ③ 注册左电机 */
    if (s != EFW_OK) return s;
    return efw_actuator_register(&g_right_motor); /* ④ 注册右电机 */
}

/**
 * @brief 设置模拟数字循迹状态 (仿真用)
 *
 * 真实项目中此函数不需要存在——循迹状态由 GPIO 或 ADC 阈值化逻辑更新。
 *
 * @param values 5 通道模拟值数组，为 NULL 则安全返回
 */
void app_platform_set_line_state(const uint16_t values[APP_LINE_CHANNELS]) {
    if (!values) return;                                    /* NULL 保护 */
    for (uint8_t i = 0; i < APP_LINE_CHANNELS; ++i) {
        g_line_input.channel[i] = values[i];                /* 逐通道赋值 */
    }
}
