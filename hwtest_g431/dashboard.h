#ifndef HWTEST_DASHBOARD_H
#define HWTEST_DASHBOARD_H

/* LCD dashboard UI: 3 pages (dashboard / stress / wave+ball), B1 = page switch,
 * B2 = pause animation, B3 = PC13 toggle, B4 = border color cycle.
 * ui_task_1ms() must be called from the 1ms main loop (cooperative). */
void ui_init(void);
void ui_task_1ms(void);

#endif
