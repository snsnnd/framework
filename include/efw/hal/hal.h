/**
 * @file    hal.h
 * @brief   HAL (硬件抽象层) 注册表接口
 *
 * 本层是框架与芯片 SDK/BSP 之间的桥梁。
 *
 * 设计思路：
 *   框架核心不含任何芯片相关的寄存器操作。用户在自己的 BSP 文件中实现
 *   具体的 init/read/write/ioctl 回调，然后通过 efw_hal_register() 注册
 *   到框架中。上层（COMM、Sensor）通过名称字符串引用这些 HAL 实例。
 *
 * 支持的硬件类型 (efw_hal_type_t)：
 *   GPIO、I2C、SPI、UART、TIMER、PWM、ADC、CUSTOM(自定义)
 *
 * 每种 HAL 的操作接口 (efw_hal_ops_t)：
 *   init  - 初始化硬件（配置时钟、引脚、中断等）
 *   read  - 从硬件读取数据（buf=缓冲区, len=期望长度, actual=实际读出字节数）
 *   write - 向硬件写入数据（同上）
 *   ioctl - 通用控制接口（cmd=命令码, arg=命令参数），用于配置波特率、采样率等
 *
 * 使用流程：
 *   ① 定义自己的 HAL 上下文结构体（如 adc_ctx_t），存放硬件基地址、DMA 句柄等
 *   ② 实现 init/read/write/ioctl 回调函数
 *   ③ 填充 efw_hal_ops_t，调用 efw_hal_register() 注册
 *   ④ 上层通过 efw_hal_read("adc1", ...) 等方式访问（名称查找）
 */

#ifndef EFW_HAL_REGISTRY_H
#define EFW_HAL_REGISTRY_H

#include "efw/core/common.h"
#include <stdint.h>

/**
 * @brief HAL 硬件类型枚举
 *
 * 每个枚举值代表一类硬件外设。注册时指定 type 方便后续按类型统计/遍历。
 * EFW_HAL_CUSTOM 用于不在以上分类中的特殊硬件（如外扩 GPIO 芯片、FPGA 接口等）
 */
typedef enum {
    EFW_HAL_GPIO   = 0, /**< 通用数字 IO：引脚电平读写，方向配置 */
    EFW_HAL_I2C,        /**< I2C 总线：支持多从机地址的同步串行通信 */
    EFW_HAL_SPI,        /**< SPI 总线：高速全双工同步串行通信 */
    EFW_HAL_UART,       /**< UART 串口：异步串行通信 (TTL/RS232/RS485) */
    EFW_HAL_TIMER,      /**< 定时器：微秒/毫秒级定时、PWM 时基、编码器计数 */
    EFW_HAL_PWM,        /**< PWM 输出：占空比控制 (电机调速、LED 亮度、舵机角度) */
    EFW_HAL_ADC,        /**< ADC 模数转换：模拟电压采集 (传感器、电池电压监测) */
    EFW_HAL_CUSTOM      /**< 自定义外设：不在以上分类的硬件 (DAC、CAN 控制器、FPGA 桥等) */
} efw_hal_type_t;

/**
 * @brief HAL 操作接口结构体（每个已注册的 HAL 实例对应一个此结构体）
 *
 * 所有字段在注册时由用户填充，注册后由框架只读管理。
 *
 * @field name     全局唯一名称 (如 "adc1", "uart2", "i2c_sensors")
 *                 上层通过此名称引用该 HAL 实例
 * @field type     硬件类型 (efw_hal_type_t)，用于分类统计
 * @field bus_id   总线编号 (如 UART2 的 bus_id=2)，由用户定义，框架不做解释
 *                 同一芯片可能有多个同类型外设，bus_id 用于区分
 * @field ctx      用户私有上下文指针 (如指向 adc_ctx_t 的指针)
 *                 所有回调函数的第一个参数，框架完全不关心其内容
 * @field init     硬件初始化回调 (可空，空则跳过)
 *                 典型操作：使能时钟、配置 GPIO 复用、设置 DMA、使能中断
 * @field read     硬件读取回调 (可空，但上层调用 efw_hal_read 时会返回 EFW_ERR_INVALID)
 *                 buf=存放读取数据的缓冲区, len=期望读取字节数, actual=实际读取字节数
 * @field write    硬件写入回调 (可空，同上)
 *                 buf=待写入数据, len=期望写入字节数, actual=实际写入字节数
 * @field ioctl    硬件控制回调 (可空)
 *                 cmd=命令码 (用户自定义), arg=命令参数指针
 *                 典型用途：设置波特率、切换采样通道、配置中断触发条件
 */
typedef struct {
    const char *name;       /**< 全局唯一名称标识 */
    efw_hal_type_t type;    /**< 硬件类型 */
    uint8_t bus_id;         /**< 总线编号 (如 1 表示 UART1, I2C1 等) */
    void *ctx;              /**< 用户私有上下文 (指向芯片外设句柄等) */
    efw_status_t (*init)(void *ctx);    /**< 初始化回调 */
    efw_status_t (*read)(void *ctx, void *buf, uint16_t len, uint16_t *actual);  /**< 读取回调 */
    efw_status_t (*write)(void *ctx, const void *buf, uint16_t len, uint16_t *actual); /**< 写入回调 */
    efw_status_t (*ioctl)(void *ctx, uint32_t cmd, void *arg); /**< 通用控制回调 */
} efw_hal_ops_t;

/* ====== HAL 注册表 API ====== */

efw_status_t efw_hal_registry_init(void);
efw_status_t efw_hal_registry_init_pool(const efw_hal_ops_t **pool, size_t capacity);
efw_status_t efw_hal_register(const efw_hal_ops_t *ops);
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops);
efw_status_t efw_hal_unregister(const char *name);
size_t efw_hal_count(void);
typedef void (*efw_hal_enumerate_fn)(const efw_hal_ops_t *ops, void *user);
void efw_hal_enumerate(efw_hal_enumerate_fn fn, void *user);
efw_status_t efw_hal_init_device(const char *name);
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg);

#endif
