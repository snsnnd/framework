/**
 * @file    comm.h
 * @brief   COMM (通信抽象层) 注册表接口
 *
 * 本层位于 HAL 之上，封装通信协议语义。
 *
 * HAL vs COMM 的区别：
 *   HAL 关注 "怎么把字节发出去" (操作寄存器)
 *   COMM 关注 "以什么协议收发" (帧格式、握手、校验)
 *
 * 例如 UART：
 *   HAL 层 = UART 外设驱动 (使能时钟、配置波特率、发一个字节)
 *   COMM 层 = 基于 UART 的通信协议 (如 Modbus 帧、自定义二进制协议)
 *
 * 绑定机制 (hal_name)：
 *   每个 COMM 必须绑定到一个已注册的 HAL。注册 COMM 时，框架会立即检查
 *   hal_name 引用的 HAL 是否已存在——不存在则注册失败（编译期绑定校验）。
 *   这确保了运行时不会出现 "引用了不存在的 HAL" 的隐蔽 bug。
 *
 * 支持的通信类型 (efw_comm_type_t)：
 *   UART、CAN、I2C、SPI、ETH(以太网)、CUSTOM(自定义)
 *
 * 每种 COMM 的操作接口 (efw_comm_ops_t)：
 *   open  - 打开通信通道 (初始化协议栈、握手)
 *   close - 关闭通信通道 (释放资源、发送断开帧)
 *   send  - 发送数据 (data=数据, len=长度, actual=实际发送字节数)
 *   recv  - 接收数据 (阻塞或非阻塞取决于底层实现)
 */

#ifndef EFW_COMM_REGISTRY_H
#define EFW_COMM_REGISTRY_H

#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include <stdint.h>

/**
 * @brief 通信类型枚举
 *
 * 与 HAL 类型名称相似但语义不同：
 *   例如 EFW_HAL_UART 表示 UART 硬件外设的寄存器级驱动
 *   而 EFW_COMM_UART 表示使用 UART 硬件进行通信的协议层
 */
typedef enum {
    EFW_COMM_UART   = 0, /**< 基于 UART 串口的通信协议 (如 Modbus、自定义二进制协议) */
    EFW_COMM_CAN,        /**< 基于 CAN 总线的通信 (如 CANopen、J1939) */
    EFW_COMM_I2C,        /**< 基于 I2C 总线的通信 (如 SMBus 协议) */
    EFW_COMM_SPI,        /**< 基于 SPI 总线的通信 (如 SPI Flash 文件系统协议) */
    EFW_COMM_ETH,        /**< 基于以太网的通信 (如 TCP/IP、UDP 应用层协议) */
    EFW_COMM_CUSTOM      /**< 自定义通信方式 (如蓝牙 BLE、LoRa、NFC 等) */
} efw_comm_type_t;

/**
 * @brief COMM 操作接口结构体
 *
 * @field name     全局唯一名称 (如 "dbg_uart", "motor_can", "sensor_i2c")
 * @field type     通信类型 (efw_comm_type_t)
 * @field hal_name 绑定到的 HAL 名称 (如 "uart1")，注册时必须已存在
 * @field ctx      用户私有上下文 (如协议栈状态机句柄、收发缓冲区指针)
 * @field open     打开通信通道回调 (可空)
 *                 典型操作：初始化协议栈、发送握手帧、启动接收 DMA
 * @field close    关闭通信通道回调 (可空)
 *                 典型操作：发送关闭帧、停止 DMA、释放缓冲区
 * @field send     发送数据回调 (必填，注册时校验)
 *                 data=待发送字节数组, len=长度, actual=实际发送字节数(输出参数)
 * @field recv     接收数据回调 (必填，注册时校验)
 *                 data=存放接收数据的缓冲区, len=期望长度, actual=实际接收字节数(输出参数)
 *                 可以返回 len < 期望值表示非阻塞读到部分数据
 */
typedef struct {
    const char *name;       /**< 全局唯一名称 */
    efw_comm_type_t type;   /**< 通信类型 */
    const char *hal_name;   /**< 绑定的 HAL 名称 (注册时做存在性校验) */
    void *ctx;              /**< 用户私有上下文 */
    efw_status_t (*open)(void *ctx);   /**< 打开通道回调 */
    efw_status_t (*close)(void *ctx);  /**< 关闭通道回调 */
    efw_status_t (*send)(void *ctx, const uint8_t *data, uint16_t len, uint16_t *actual);  /**< 发送回调 */
    efw_status_t (*recv)(void *ctx, uint8_t *data, uint16_t len, uint16_t *actual);        /**< 接收回调 */
} efw_comm_ops_t;

/* ====== COMM 注册表 API ====== */

efw_status_t efw_comm_registry_init(void);
efw_status_t efw_comm_register(const efw_comm_ops_t *ops);
efw_status_t efw_comm_get(const char *name, const efw_comm_ops_t **out_ops);
size_t efw_comm_count_by_type(efw_comm_type_t type);
efw_status_t efw_comm_bind_hal(const char *comm_name, const efw_hal_ops_t **out_hal);
efw_status_t efw_comm_open(const char *name);
efw_status_t efw_comm_close(const char *name);
efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual);
efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual);

#endif
