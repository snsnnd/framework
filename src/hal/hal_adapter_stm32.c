/**
 * @file    hal_adapter_stm32.c
 * @brief   STM32 HAL 适配层实现
 */

#include "efw/hal/hal_adapter.h"

#if EFW_BACKEND_STM32

#include <string.h>

/* ==================================================================
 *  GPIO 适配实现
 * ================================================================== */

// GPIO 端口映射表
static const struct {
    const char *name;
    GPIO_TypeDef *port;
} gpio_port_map[] = {
    {"GPIOA", GPIOA},
    {"GPIOB", GPIOB},
    {"GPIOC", GPIOC},
    {"GPIOD", GPIOD},
    {"GPIOE", GPIOE},
    {"GPIOF", GPIOF},
    {"GPIOG", GPIOG},
    {"GPIOH", GPIOH},
    {NULL, NULL}
};

// GPIO 引脚映射
static uint16_t gpio_pin_from_name(const char *name) {
    // 解析 "PA0" -> GPIO_PIN_0
    if (name[0] == 'P' && name[2] >= '0' && name[2] <= '9') {
        int pin = name[2] - '0';
        if (name[3] >= '0' && name[3] <= '9') {
            pin = pin * 10 + (name[3] - '0');
        }
        return (1 << pin);
    }
    return 0;
}

static GPIO_TypeDef* gpio_port_from_name(const char *name) {
    // 解析 "PA0" -> GPIOA
    if (name[0] == 'P') {
        char port_name[8] = "GPIO";
        port_name[4] = name[1];
        port_name[5] = '\0';
        
        for (int i = 0; gpio_port_map[i].name; i++) {
            if (strcmp(gpio_port_map[i].name, port_name) == 0) {
                return gpio_port_map[i].port;
            }
        }
    }
    return NULL;
}

efw_status_t efw_hal_gpio_init(efw_hal_gpio_t *gpio, const char *name) {
    if (!gpio || !name) return EFW_ERR_INVALID;
    
    gpio->name = name;
    gpio->port = gpio_port_from_name(name);
    gpio->pin = gpio_pin_from_name(name);
    
    if (!gpio->port || !gpio->pin) {
        return EFW_ERR_INVALID;
    }
    
    // 使能 GPIO 时钟
    if (gpio->port == GPIOA) __HAL_RCC_GPIOA_CLK_ENABLE();
    else if (gpio->port == GPIOB) __HAL_RCC_GPIOB_CLK_ENABLE();
    else if (gpio->port == GPIOC) __HAL_RCC_GPIOC_CLK_ENABLE();
    else if (gpio->port == GPIOD) __HAL_RCC_GPIOD_CLK_ENABLE();
    else if (gpio->port == GPIOE) __HAL_RCC_GPIOE_CLK_ENABLE();
    
    return EFW_OK;
}

uint8_t efw_hal_gpio_read(const efw_hal_gpio_t *gpio) {
    if (!gpio || !gpio->port) return 0;
    return HAL_GPIO_ReadPin(gpio->port, gpio->pin) ? 1 : 0;
}

void efw_hal_gpio_write(efw_hal_gpio_t *gpio, uint8_t value) {
    if (!gpio || !gpio->port) return;
    HAL_GPIO_WritePin(gpio->port, gpio->pin, value ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void efw_hal_gpio_toggle(efw_hal_gpio_t *gpio) {
    if (!gpio || !gpio->port) return;
    HAL_GPIO_TogglePin(gpio->port, gpio->pin);
}

/* ==================================================================
 *  ADC 适配实现
 * ================================================================== */

efw_status_t efw_hal_adc_init(efw_hal_adc_t *adc, const char *name) {
    if (!adc || !name) return EFW_ERR_INVALID;
    adc->name = name;
    // ADC 初始化需要在 CubeMX 或用户代码中完成
    return EFW_OK;
}

uint16_t efw_hal_adc_read(const efw_hal_adc_t *adc) {
    if (!adc || !adc->hadc) return 0;
    
    HAL_ADC_Start(adc->hadc);
    HAL_ADC_PollForConversion(adc->hadc, 10);
    uint16_t value = HAL_ADC_GetValue(adc->hadc);
    HAL_ADC_Stop(adc->hadc);
    
    return value;
}

uint32_t efw_hal_adc_read_voltage(const efw_hal_adc_t *adc) {
    uint16_t raw = efw_hal_adc_read(adc);
    // 假设 3.3V 参考电压，12位分辨率
    return (uint32_t)(raw * 3300 / 4095);
}

/* ==================================================================
 *  PWM 适配实现
 * ================================================================== */

efw_status_t efw_hal_pwm_init(efw_hal_pwm_t *pwm, const char *name, uint32_t freq) {
    if (!pwm || !name) return EFW_ERR_INVALID;
    pwm->name = name;
    pwm->frequency = freq;
    pwm->duty = 0;
    return EFW_OK;
}

void efw_hal_pwm_set_duty(efw_hal_pwm_t *pwm, uint32_t duty) {
    if (!pwm || !pwm->htim) return;
    
    pwm->duty = duty;
    uint32_t period = __HAL_TIM_GET_AUTORELOAD(pwm->htim);
    uint32_t pulse = (period * duty) / 10000;
    
    __HAL_TIM_SET_COMPARE(pwm->htim, pwm->channel, pulse);
}

void efw_hal_pwm_start(efw_hal_pwm_t *pwm) {
    if (!pwm || !pwm->htim) return;
    HAL_TIM_PWM_Start(pwm->htim, pwm->channel);
}

void efw_hal_pwm_stop(efw_hal_pwm_t *pwm) {
    if (!pwm || !pwm->htim) return;
    HAL_TIM_PWM_Stop(pwm->htim, pwm->channel);
}

/* ==================================================================
 *  UART 适配实现
 * ================================================================== */

efw_status_t efw_hal_uart_init(efw_hal_uart_t *uart, const char *name, uint32_t baud) {
    if (!uart || !name) return EFW_ERR_INVALID;
    uart->name = name;
    uart->baudrate = baud;
    return EFW_OK;
}

efw_status_t efw_hal_uart_send(efw_hal_uart_t *uart, const uint8_t *data, uint16_t len) {
    if (!uart || !uart->huart || !data) return EFW_ERR_INVALID;
    
    HAL_StatusTypeDef status = HAL_UART_Transmit(uart->huart, (uint8_t*)data, len, 100);
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}

efw_status_t efw_hal_uart_receive(efw_hal_uart_t *uart, uint8_t *data, uint16_t len, uint16_t *actual) {
    if (!uart || !uart->huart || !data || !actual) return EFW_ERR_INVALID;
    
    uint16_t received = 0;
    HAL_StatusTypeDef status = HAL_UART_Receive(uart->huart, data, len, 10);
    
    if (status == HAL_OK) {
        received = len;
    } else if (status == HAL_TIMEOUT) {
        // 获取已接收的数据量
        received = len - __HAL_UART_GET_FLAG(uart->huart, UART_FLAG_RXNE);
    }
    
    *actual = received;
    return (status == HAL_OK || status == HAL_TIMEOUT) ? EFW_OK : EFW_ERR_IO;
}

/* ==================================================================
 *  I2C 适配实现
 * ================================================================== */

efw_status_t efw_hal_i2c_init(efw_hal_i2c_t *i2c, const char *name, uint32_t speed) {
    if (!i2c || !name) return EFW_ERR_INVALID;
    i2c->name = name;
    i2c->speed = speed;
    return EFW_OK;
}

efw_status_t efw_hal_i2c_write(efw_hal_i2c_t *i2c, uint8_t addr, const uint8_t *data, uint16_t len) {
    if (!i2c || !i2c->hi2c || !data) return EFW_ERR_INVALID;
    
    HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(i2c->hi2c, addr << 1, (uint8_t*)data, len, 100);
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}

efw_status_t efw_hal_i2c_read(efw_hal_i2c_t *i2c, uint8_t addr, uint8_t *data, uint16_t len) {
    if (!i2c || !i2c->hi2c || !data) return EFW_ERR_INVALID;
    
    HAL_StatusTypeDef status = HAL_I2C_Master_Receive(i2c->hi2c, addr << 1, data, len, 100);
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}

/* ==================================================================
 *  SPI 适配实现
 * ================================================================== */

efw_status_t efw_hal_spi_init(efw_hal_spi_t *spi, const char *name, uint32_t speed) {
    if (!spi || !name) return EFW_ERR_INVALID;
    spi->name = name;
    spi->speed = speed;
    return EFW_OK;
}

efw_status_t efw_hal_spi_transfer(efw_hal_spi_t *spi, const uint8_t *tx, uint8_t *rx, uint16_t len) {
    if (!spi || !spi->hspi) return EFW_ERR_INVALID;
    
    HAL_StatusTypeDef status = HAL_SPI_TransmitReceive(spi->hspi, (uint8_t*)tx, rx, len, 100);
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}

/* ==================================================================
 *  定时器适配实现
 * ================================================================== */

efw_status_t efw_hal_timer_init(efw_hal_timer_t *timer, const char *name, uint32_t period_us) {
    if (!timer || !name) return EFW_ERR_INVALID;
    timer->name = name;
    timer->period_us = period_us;
    return EFW_OK;
}

void efw_hal_timer_start(efw_hal_timer_t *timer) {
    if (!timer || !timer->htim) return;
    HAL_TIM_Base_Start_IT(timer->htim);
}

void efw_hal_timer_stop(efw_hal_timer_t *timer) {
    if (!timer || !timer->htim) return;
    HAL_TIM_Base_Stop_IT(timer->htim);
}

/* ==================================================================
 *  系统函数实现
 * ================================================================== */

uint32_t efw_hal_get_time_us(void) {
    return HAL_GetTick() * 1000 + (SysTick->LOAD - SysTick->VAL) / (SystemCoreClock / 1000000);
}

void efw_hal_delay_ms(uint32_t ms) {
    HAL_Delay(ms);
}

void efw_hal_delay_us(uint32_t us) {
    uint32_t start = efw_hal_get_time_us();
    while ((efw_hal_get_time_us() - start) < us) {
        // 忙等待
    }
}

#endif /* EFW_BACKEND_STM32 */
