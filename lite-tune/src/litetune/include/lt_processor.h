#ifndef LT_PROCESSOR_H
#define LT_PROCESSOR_H

#include "lt_common.h"
#include "lt_rx.h"
#include "lt_state.h"
#include "lt_tx.h"


#ifdef __cplusplus
extern "C" {
#endif

LT_API void lt_process(void);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

LT_API void lt_process(void)
{
    lt_state_t state = lt_state_get();

    if ((state == LT_STATE_UNINIT) || (state == LT_STATE_REGISTERING)) {
        return;
    }

    lt_rx_ring_process();
    lt_tx_try_send();
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_PROCESSOR_H */
