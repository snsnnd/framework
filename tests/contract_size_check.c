#include <stddef.h>
#include <stdint.h>

#include "efw/efw.h"

#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
#define EFW_CONTRACT_STATIC_ASSERT(condition, message) _Static_assert((condition), message)
#else
#define EFW_CONTRACT_STATIC_ASSERT_JOIN_(a, b) a##b
#define EFW_CONTRACT_STATIC_ASSERT_JOIN(a, b) EFW_CONTRACT_STATIC_ASSERT_JOIN_(a, b)
#define EFW_CONTRACT_STATIC_ASSERT(condition, message) \
    typedef char EFW_CONTRACT_STATIC_ASSERT_JOIN(efw_contract_static_assert_, __LINE__)[(condition) ? 1 : -1]
#endif

EFW_CONTRACT_STATIC_ASSERT(sizeof(efw_pid_input_t) == 16u, "efw_pid_input_t contract size mismatch");
EFW_CONTRACT_STATIC_ASSERT(sizeof(efw_pid_output_t) == 12u, "efw_pid_output_t contract size mismatch");
EFW_CONTRACT_STATIC_ASSERT(sizeof(efw_motor_cmd_t) == 8u, "efw_motor_cmd_t contract size mismatch");
EFW_CONTRACT_STATIC_ASSERT(sizeof(efw_line_tracking_data_t) == 18u, "efw_line_tracking_data_t contract size mismatch");

#define EFW_CONTRACT_ALIGNOF(type) offsetof(struct { char c; type value; }, value)

EFW_CONTRACT_STATIC_ASSERT(EFW_CONTRACT_ALIGNOF(efw_pid_input_t) == 4u, "efw_pid_input_t contract align mismatch");
EFW_CONTRACT_STATIC_ASSERT(EFW_CONTRACT_ALIGNOF(efw_pid_output_t) == 4u, "efw_pid_output_t contract align mismatch");
EFW_CONTRACT_STATIC_ASSERT(EFW_CONTRACT_ALIGNOF(efw_motor_cmd_t) == 4u, "efw_motor_cmd_t contract align mismatch");
EFW_CONTRACT_STATIC_ASSERT(EFW_CONTRACT_ALIGNOF(efw_line_tracking_data_t) == 2u, "efw_line_tracking_data_t contract align mismatch");

int main(void) {
    return 0;
}
