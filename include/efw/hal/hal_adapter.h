/**
 * @file    efw_hal_adapter.h
 * @brief   EFW HAL 适配层 - 将 EFW HAL 接口映射到固件库
 *
 * 支持多种固件库：
 * - STM32 HAL/LL 库
 * - ESP-IDF
 * - 裸机寄存器
 */

#ifndef EFW_HAL_ADAPTER_H
#define EFW_HAL_ADAPTER_H

#include "efw/core/common.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  固件库选择（通过编译宏定义）
 * ================================================================== */

#if defined(USE_STM32_HAL)
    #include "stm32f4xx_hal.h"
    #define EFW_BACKEND_STM32 1
#elif defined(USE_ESP_IDF)
    #include "driver/gpio.h"
    #include "driver/adc.h"
    #define EFW_BACKEND_ESP32 1
#else
    #define EFW_BACKEND_BAREMETAL 1
#endif

/* ==================================================================
 *  GPIO 适配
 * ================================================================== */

/** @brief GPIO 端口定义 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    GPIO_TypeDef *port;
    uint16_t pin;
#elif EFW_BACKEND_ESP32
    gpio_num_t gpio_num;
#else
    volatile uint32_t *reg;
    uint32_t bit;
#endif
} efw_hal_gpio_t;

/**
 * @brief 初始化 GPIO
 */
efw_status_t efw_hal_gpio_init(efw_hal_gpio_t *gpio, const char *name);

/**
 * @brief 读取 GPIO
 */
uint8_t efw_hal_gpio_read(const efw_hal_gpio_t *gpio);

/**
 * @brief 写入 GPIO
 */
void efw_hal_gpio_write(efw_hal_gpio_t *gpio, uint8_t value);

/**
 * @brief 切换 GPIO
 */
void efw_hal_gpio_toggle(efw_hal_gpio_t *gpio);

/* ==================================================================
 *  ADC 适配
 * ================================================================== */

/** @brief ADC 配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    ADC_HandleTypeDef *hadc;
    uint32_t channel;
#elif EFW_BACKEND_ESP32
    adc_channel_t channel;
#else
    volatile uint32_t *reg;
#endif
} efw_hal_adc_t;

/**
 * @brief 初始化 ADC
 */
efw_status_t efw_hal_adc_init(efw_hal_adc_t *adc, const char *name);

/**
 * @brief 读取 ADC 值
 */
uint16_t efw_hal_adc_read(const efw_hal_adc_t *adc);

/**
 * @brief 读取 ADC 电压 (mV)
 */
uint32_t efw_hal_adc_read_voltage(const efw_hal_adc_t *adc);

/* ==================================================================
 *  PWM 适配
 * ================================================================== */

/** @brief PWM 配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    TIM_HandleTypeDef *htim;
    uint32_t channel;
#elif EFW_BACKEND_ESP32
    ledc_channel_t channel;
#else
    volatile uint32_t *duty_reg;
#endif
    uint32_t frequency;
    uint32_t duty;
} efw_hal_pwm_t;

/**
 * @brief 初始化 PWM
 */
efw_status_t efw_hal_pwm_init(efw_hal_pwm_t *pwm, const char *name, uint32_t freq);

/**
 * @brief 设置 PWM 占空比 (0-10000 = 0%-100.00%)
 */
void efw_hal_pwm_set_duty(efw_hal_pwm_t *pwm, uint32_t duty);

/**
 * @brief 启动 PWM
 */
void efw_hal_pwm_start(efw_hal_pwm_t *pwm);

/**
 * @brief 停止 PWM
 */
void efw_hal_pwm_stop(efw_hal_pwm_t *pwm);

/* ==================================================================
 *  UART 适配
 * ================================================================== */

/** @brief UART 配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    UART_HandleTypeDef *huart;
#elif EFW_BACKEND_ESP32
    int uart_num;
#else
    volatile uint32_t *tx_reg;
    volatile uint32_t *rx_reg;
#endif
    uint32_t baudrate;
} efw_hal_uart_t;

/**
 * @brief 初始化 UART
 */
efw_status_t efw_hal_uart_init(efw_hal_uart_t *uart, const char *name, uint32_t baud);

/**
 * @brief 发送数据
 */
efw_status_t efw_hal_uart_send(efw_hal_uart_t *uart, const uint8_t *data, uint16_t len);

/**
 * @brief 接收数据
 */
efw_status_t efw_hal_uart_receive(efw_hal_uart_t *uart, uint8_t *data, uint16_t len, uint16_t *actual);

/* ==================================================================
 *  I2C 适配
 * ================================================================== */

/** @brief I2C 配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    I2C_HandleTypeDef *hi2c;
#elif EFW_BACKEND_ESP32
    int i2c_num;
#else
    volatile uint32_t *reg;
#endif
    uint32_t speed;
} efw_hal_i2c_t;

/**
 * @brief 初始化 I2C
 */
efw_status_t efw_hal_i2c_init(efw_hal_i2c_t *i2c, const char *name, uint32_t speed);

/**
 * @brief I2C 写入
 */
efw_status_t efw_hal_i2c_write(efw_hal_i2c_t *i2c, uint8_t addr, const uint8_t *data, uint16_t len);

/**
 * @brief I2C 读取
 */
efw_status_t efw_hal_i2c_read(efw_hal_i2c_t *i2c, uint8_t addr, uint8_t *data, uint16_t len);

/* ==================================================================
 *  SPI 适配
 * ================================================================== */

/** @brief SPI 配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    SPI_HandleTypeDef *hspi;
#elif EFW_BACKEND_ESP32
    int spi_num;
#else
    volatile uint32_t *reg;
#endif
    uint32_t speed;
} efw_hal_spi_t;

/**
 * @brief 初始化 SPI
 */
efw_status_t efw_hal_spi_init(efw_hal_spi_t *spi, const char *name, uint32_t speed);

/**
 * @brief SPI 传输
 */
efw_status_t efw_hal_spi_transfer(efw_hal_spi_t *spi, const uint8_t *tx, uint8_t *rx, uint16_t len);

/* ==================================================================
 *  定时器适配
 * ================================================================== */

/** @brief 定时器配置 */
typedef struct {
    const char *name;
#if EFW_BACKEND_STM32
    TIM_HandleTypeDef *htim;
#elif EFW_BACKEND_ESP32
    int timer_group;
    int timer_idx;
#else
    volatile uint32_t *reg;
#endif
    uint32_t period_us;
    void (*callback)(void);
} efw_hal_timer_t;

/**
 * @brief 初始化定时器
 */
efw_status_t efw_hal_timer_init(efw_hal_timer_t *timer, const char *name, uint32_t period_us);

/**
 * @brief 启动定时器
 */
void efw_hal_timer_start(efw_hal_timer_t *timer);

/**
 * @brief 停止定时器
 */
void efw_hal_timer_stop(efw_hal_timer_t *timer);

/* ==================================================================
 *  系统函数
 * ================================================================== */

/**
 * @brief 获取系统时间 (微秒)
 */
uint32_t efw_hal_get_time_us(void);

/**
 * @brief 延时 (毫秒)
 */
void efw_hal_delay_ms(uint32_t ms);

/**
 * @brief 延时 (微秒)
 */
void efw_hal_delay_us(uint32_t us);

#ifdef __cplusplus
}
#endif

#endif /* EFW_HAL_ADAPTER_H */
