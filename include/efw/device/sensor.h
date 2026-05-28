/**
 * @file    sensor.h
 * @brief   Device (传感器设备层) 注册表接口
 *
 * 本层抽象具体的传感器设备。框架内置了 5 种传感器类型，用户也可以
 * 通过 EFW_SENSOR_CUSTOM 扩展任意自定义传感器。
 *
 * 可注册的传感器类型 (efw_sensor_type_t)：
 *   ┌─────────────────────────┬────────────────────────────────────────┐
 *   │ EFW_SENSOR_LINE_TRACKING │ 循迹传感器 (灰度/红外反射阵列)          │
 *   │ EFW_SENSOR_IMU           │ 惯性测量单元 (加速度计+陀螺仪+磁力计)   │
 *   │ EFW_SENSOR_ENCODER       │ 编码器 (旋转编码器/正交编码器)          │
 *   │ EFW_SENSOR_ULTRASONIC    │ 超声波距离传感器 (HC-SR04 等)           │
 *   │ EFW_SENSOR_CUSTOM        │ 自定义传感器 (颜色、气压、电流等)       │
 *   └─────────────────────────┴────────────────────────────────────────┘
 *
 * IO 绑定机制 (双通道)：
 *   每个传感器可以绑定到一个 HAL（如 ADC 读电压）或一个 COMM（如 I2C 读寄存器），
 *   也可以 HAL 和 COMM 都不绑（纯软件计算的虚拟传感器）。
 *   注册时框架会校验引用的 hal_name/comm_name 是否已存在。
 *
 * channel_count 字段：
 *   用于区分同类型不同规格的传感器。例如循迹模块有 4 路和 8 路两种，
 *   它们 type 都是 EFW_SENSOR_LINE_TRACKING，但 channel_count 分别为 4 和 8。
 *   这个字段由用户定义，框架不做校验——具体含义由 read 回调中的逻辑负责。
 *
 * 使用流程：
 *   ① 实现传感器的 init 和 read 回调（内部调用 HAL 或 COMM API 完成实际 IO）
 *   ② 填充 efw_sensor_ops_t，指定 hal_name 或 comm_name
 *   ③ 调用 efw_sensor_register() 注册
 *   ④ 运行时调用 efw_sensor_read("sensor_name", &output) 获取数据
 */

#ifndef EFW_SENSOR_REGISTRY_H
#define EFW_SENSOR_REGISTRY_H

#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include "efw/comm/comm.h"

/**
 * @brief 传感器类型枚举
 */
typedef enum {
    EFW_SENSOR_LINE_TRACKING = 0, /**< 循迹传感器：灰度/红外反射阵列，返回多路模拟/数字值 */
    EFW_SENSOR_IMU,               /**< 惯性测量单元：加速度计+陀螺仪(+磁力计)，返回姿态/角速度 */
    EFW_SENSOR_ENCODER,           /**< 编码器：旋转编码器 (增量式/绝对式)，返回脉冲计数或角度 */
    EFW_SENSOR_ULTRASONIC,        /**< 超声波传感器：HC-SR04 等，返回距离值 (cm/mm) */
    EFW_SENSOR_CUSTOM             /**< 自定义传感器：颜色传感器、气压计、电流传感器等 */
} efw_sensor_type_t;

/**
 * @brief 传感器操作接口结构体
 *
 * @field name          全局唯一名称 (如 "line4", "imu_head", "enc_left")
 * @field type          传感器类型 (efw_sensor_type_t)
 * @field channel_count 通道数 (如 4 路循迹 = 4，三轴 IMU = 3)
 *                      仅用于区分同类不同规格的传感器，框架不做逻辑校验
 * @field hal_name      绑定的 HAL 名称 (可空，如 "adc1")，注册时校验存在性
 * @field comm_name     绑定的 COMM 名称 (可空，如 "imu_i2c")，注册时校验存在性
 *                      hal_name 和 comm_name 至少填一个 (纯软件传感器可都不填)
 * @field ctx           用户私有上下文 (如存储传感器校准参数、原始数据缓冲区的结构体)
 * @field init          传感器初始化回调 (可空)
 *                      典型操作：写配置寄存器、设置量程/采样率、校准零点
 * @field read          传感器读取回调 (必填，注册时校验)
 *                      从硬件获取数据并填充到 out 指向的输出结构体
 *                      out 的类型由用户定义（如 float* 或自定义结构体指针）
 */
typedef struct {
    const char *name;           /**< 全局唯一名称 */
    efw_sensor_type_t type;     /**< 传感器类型 */
    uint8_t channel_count;      /**< 通道数 (用户定义，仅作标记) */
    const char *hal_name;       /**< 绑定的 HAL 名称 (可空) */
    const char *comm_name;      /**< 绑定的 COMM 名称 (可空) */
    void *ctx;                  /**< 用户私有上下文 */
    efw_status_t (*init)(void *ctx);            /**< 初始化回调 */
    efw_status_t (*read)(void *ctx, void *out);  /**< 读取回调 (必填) */
} efw_sensor_ops_t;

/* ====== 传感器注册表 API ====== */

efw_status_t efw_sensor_registry_init(void);
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops);
efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops);
size_t efw_sensor_count_by_type(efw_sensor_type_t type);
efw_status_t efw_sensor_bind_hal(const char *sensor_name, const efw_hal_ops_t **out_hal);
efw_status_t efw_sensor_bind_comm(const char *sensor_name, const efw_comm_ops_t **out_comm);
efw_status_t efw_sensor_init_device(const char *name);
efw_status_t efw_sensor_read(const char *name, void *out);

#endif
