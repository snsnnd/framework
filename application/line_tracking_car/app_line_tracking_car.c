/**
 * @file    app_line_tracking_car.c
 * @brief   应用层实现 —— 循迹小车的初始化和主控制循环
 *
 * 本文件是三层架构中的"应用层"实现。
 *
 * =========================================================================
 * efw_line_tracking_follow_diff() —— 框架最高层 API
 * =========================================================================
 *
 *   这个函数将循迹控制的 4 个步骤封装为一次调用：
 *
 *     ① 读取循迹传感器 → efw_line_tracking_read(sensor_name, &data)
 *     ② 计算加权误差  → efw_line_tracking_error_weighted(&data, weights)
 *     ③ 运行 PID       → efw_algo_run(pid_name, &in, &out)
 *     ④ 差速驱动电机   → efw_motor_set_diff(left, right, base_speed, turn)
 *
 *   参数：
 *     sensor_name = "line_sensor_5ch"  → 5 通道循迹传感器
 *     pid_name    = "line_pid"         → PD 控制器 (Kp=18, Ki=0, Kd=2.5)
 *     left_motor  = "left_motor"       → 左电机
 *     right_motor = "right_motor"      → 右电机
 *     weights     = {-2,-1,0,1,2}      → 5 通道等距权重
 *     base_speed  = 45.0f              → 基础巡航速度
 *     dt          = 0.001f             → 控制周期 1ms
 *     out_error   = 0                  → 不需要输出 error
 *     out_turn    = 0                  → 不需要输出 turn
 *
 *   如果不需要自动差速 (如使用舵机转向)，可以改用多个单独调用组合。
 *
 * =========================================================================
 * 参数调节方法 (按优先级)
 * =========================================================================
 *
 *   【PID 参数 — 最主要的调参入口】
 *     Kp (默认 18.0) — 弯道响应
 *       太小 → 弯道转向不足，车冲出赛道；太大 → 直道摇摆
 *     Kd (默认 2.5) — 直道稳定
 *       太小 → 直道蛇形；太大 → 高频微调、电机发热
 *     Ki (默认 0.0) — 循迹保持为 0 即可
 *
 *   【权重数组 — 影响偏差计算的灵敏度】
 *     范围大小决定 error 输出的量级，与 Kp 共同决定响应强度。
 *     推荐固定 weights={-2,-1,0,1,2}，只调 Kp/Kd。
 *
 *   【base_speed — 基础巡航速度】
 *     值越大车越快，但留给转弯的"速度裕量"越小。
 *     base_speed 应 > PID.out_max (当前 45.0 > 60 不满足!
 *     建议增大 base_speed 到 65+ 或减小 out_max)
 *
 * =========================================================================
 * 定时器中断调用 (嵌入式部署)
 * =========================================================================
 *
 *   真实项目中，app_line_tracking_car_loop_1ms() 应在 1ms 定时器中断
 *   服务程序中调用，而不是 main() 中只调用一次：
 *
 *     void TIM1_IRQHandler(void) {  // 1ms 定时器中断
 *         app_line_tracking_car_loop_1ms();
 *     }
 *
 *   1ms 控制周期意味着：
 *     - 每毫秒传感器读取一次
 *     - 每毫秒 PID 计算一次
 *     - 每毫秒电机指令更新一次
 *   这对于小车循迹来说绰绰有余 (电机响应时间通常在 10~100ms)。
 */

#include "app_line_tracking_car.h"
#include "app_board_config.h"
#include "app_components.h"
#include "app_platform.h"

static efw_line_follower_t g_line_follower;

/**
 * @brief 循迹小车初始化
 *
 * 初始化顺序 (不可调换)：
 *   ① efw_init() — 初始化 7 个注册表 (HAL→COMM→MODULE→SENSOR→ACTUATOR→ALGO→SM)
 *   ② app_platform_register() — 注册硬件 (HAL/传感器/电机)
 *   ③ app_components_register() — 注册算法 (PID)
 *
 * Fail-fast：任一步失败立即返回。
 */
efw_status_t app_line_tracking_car_init(void) {
    efw_status_t s;

    s = efw_init();                          /* ① 框架初始化 */
    if (s != EFW_OK) return s;
    s = app_platform_register();             /* ② 平台层注册 (硬件) */
    if (s != EFW_OK) return s;
    s = app_components_register();           /* ③ 组件层注册 (算法) */
    if (s != EFW_OK) return s;

    {
        static const float line_weights[APP_LINE_CHANNELS] = { -2.0f, -1.0f, 0.0f, 1.0f, 2.0f };
        return efw_line_follower_bind(&g_line_follower,
                                      "line_sensor_5ch",
                                      "line_pid",
                                      "left_motor",
                                      "right_motor",
                                      line_weights,
                                      APP_LINE_BASE_SPEED,
                                      APP_LINE_MIN_SPEED,
                                      APP_LINE_MAX_SPEED,
                                      APP_LINE_DT_SECONDS);
    }
}

/**
 * @brief 循迹小车 1ms 主控制循环
 *
 * ★ 这是整个应用的核心函数。每 1ms 调用一次。
 *
 * 使用框架的 efw_line_tracking_follow_diff() 一步完成所有操作：
 *   - 读取 5 通道传感器
 *   - 加权误差计算 (weights = {-2,-1,0,1,2})
 *   - PID 运算 (setpoint=0 = 黑线居中)
 *   - 差速驱动 (left = 45-turn, right = 45+turn)
 *
 * @return EFW_OK 成功, 否则返回错误码
 */
efw_status_t app_line_tracking_car_loop_1ms(void) {
    return efw_line_follower_update(&g_line_follower, 0, 0);
}
