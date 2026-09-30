/**
 * @file    imu.h
 * @brief   IMU (惯性测量单元) 传感器的标准化数据结构
 *
 * =========================================================================
 * IMU 是什么？
 * =========================================================================
 *
 *   IMU (Inertial Measurement Unit) 是惯性测量单元的缩写，通常包含：
 *     - 加速度计 (Accelerometer)：测量线性加速度 (m/s² 或 g)
 *     - 陀螺仪 (Gyroscope)：测量角速度 (°/s 或 rad/s)
 *     - (可选) 磁力计 (Magnetometer)：测量地磁场方向 (μT 或 Gauss)
 *
 *   常见芯片：MPU6050, MPU9250, ICM-20948, BMI160, LSM6DS3 等。
 *   通信接口：I2C 或 SPI（通过框架的 COMM 层封装）。
 *
 *   融合姿态角 (roll/pitch/yaw)：
 *     原始加速度计和陀螺仪数据需要通过传感器融合算法（如互补滤波、
 *     卡尔曼滤波、Mahony/Madgwick 算法）才能得到可靠的姿态角。
 *     本结构体中的 roll/pitch/yaw 字段是预留给上层填充的——
 *     如果传感器自带 DMP (Digital Motion Processor) 可直接输出姿态角，
 *     否则需要用户在 read 回调或上层算法中自行计算。
 *
 * =========================================================================
 * 各字段物理含义
 * =========================================================================
 *
 *   ax/ay/az — 加速度 (Acceleration)
 *     ax=沿 X 轴加速度, ay=沿 Y 轴, az=沿 Z 轴
 *     静止水平放置时：ax≈0, ay≈0, az≈1g≈9.8 m/s²（重力加速度）
 *     自由落体时：ax=ay=az=0（失重状态）
 *
 *   gx/gy/gz — 角速度 (Gyroscope)
 *     gx=绕 X 轴旋转角速度 (roll rate), gy=绕 Y 轴 (pitch rate), gz=绕 Z 轴 (yaw rate)
 *     静止时三轴都≈0
 *
 *   mx/my/mz — 地磁 (Magnetometer, 可选)
 *     指向地磁北极的方向分量，用于修正 yaw 角漂移
 *
 *   roll  — 横滚角：绕 X 轴旋转角度 (-180° ~ +180°)
 *           正值 = 右侧下沉（右滚）
 *   pitch — 俯仰角：绕 Y 轴旋转角度 (-90° ~ +90°)
 *           正值 = 头部上仰
 *   yaw   — 偏航角：绕 Z 轴旋转角度 (0° ~ 360° 或 -180° ~ +180°)
 *           0° = 指向磁北/初始方向
 */

#ifndef EFW_SENSOR_IMU_H
#define EFW_SENSOR_IMU_H

#include "efw/core/common.h"

/**
 * @brief IMU 传感器数据结构 (12 个 float 字段)
 *
 * @field ax      X 轴加速度 (m/s² 或 g，单位由实现定义)
 * @field ay      Y 轴加速度
 * @field az      Z 轴加速度 (静止水平时 ≈ +1g)
 * @field gx      X 轴角速度 (°/s 或 rad/s)
 * @field gy      Y 轴角速度
 * @field gz      Z 轴角速度
 * @field mx      X 轴磁场强度 (μT 或 Gauss，可选，无磁力计则填 0)
 * @field my      Y 轴磁场强度
 * @field mz      Z 轴磁场强度
 * @field roll    横滚角 (度)，绕 X 轴，正值=右侧下沉
 * @field pitch   俯仰角 (度)，绕 Y 轴，正值=头部上仰
 * @field yaw     偏航角 (度)，绕 Z 轴，正值=顺时针旋转
 */
typedef struct {
    float ax;        /**< X 轴加速度 */
    float ay;        /**< Y 轴加速度 */
    float az;        /**< Z 轴加速度 (含重力) */
    float gx;        /**< X 轴角速度 (roll rate) */
    float gy;        /**< Y 轴角速度 (pitch rate) */
    float gz;        /**< Z 轴角速度 (yaw rate) */
    float mx;        /**< X 轴磁场强度 (可选) */
    float my;        /**< Y 轴磁场强度 (可选) */
    float mz;        /**< Z 轴磁场强度 (可选) */
    float roll;      /**< 横滚角 (度) — 融合后姿态 */
    float pitch;     /**< 俯仰角 (度) — 融合后姿态 */
    float yaw;       /**< 偏航角 (度) — 融合后姿态 */
} efw_imu_data_t;

/**
 * @brief 读取 IMU 传感器数据
 *
 * 内部委托给通用 efw_sensor_read()。
 * 用户需要在注册的 IMU 传感器的 read 回调中填充所有 12 个字段。
 *
 * @param name 传感器注册名称 (如 "imu_head", "imu_body")
 * @param out  输出数据指针 (efw_imu_data_t*，不能为空)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数错误
 */
efw_status_t efw_imu_read(const char *name, efw_imu_data_t *out);

#endif
