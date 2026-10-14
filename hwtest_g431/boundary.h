#ifndef HWTEST_BOUNDARY_H
#define HWTEST_BOUNDARY_H

/* Boundary hunt: frequency sweep (incl. mild overclock), scheduler starvation,
 * event saturation, UART throughput, stack high-water. MCU only. */
void boundary_run_all(void);

#endif
