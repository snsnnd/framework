#ifndef HWTEST_STRESS_H
#define HWTEST_STRESS_H

#include <stdint.h>

typedef struct {
    uint32_t pub_ns;          /* sync topic publish ns (4 subscribers) */
    uint32_t queue_rt_ns;     /* event queue post+process roundtrip ns */
    uint32_t pid_ops_s;       /* pid registry runs per second */
    uint32_t fuzz_ops;        /* ds fuzz op count */
    uint32_t fuzz_bad;        /* ds fuzz invariant violations */
    uint32_t lookup3_ns;      /* sensor lookup ns with 3 entries */
    uint32_t lookup32_ns;     /* sensor lookup ns with 32 entries */
    uint32_t sched16_ms;      /* wall ms for 200ms of 16-task schedule */
    uint32_t cap_sensor;      /* capacity reached */
    uint32_t cap_hal;
    uint32_t cap_actuator;
    uint32_t cap_algo;
    uint32_t cap_module;
    uint32_t cap_sm;
    uint32_t cap_sched;
    uint32_t soak_errors;     /* diag errors during soak */
} stress_results_t;

extern stress_results_t g_stress;

void stress_run_all(void);

#endif
