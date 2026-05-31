/**
 * @file    ds.h
 * @brief   EFW 基础数据结构：字节环形缓冲区、固定长度队列、固定长度栈
 *
 * 所有结构都由调用方提供存储空间，不使用动态内存，不依赖 OS，适合裸机/RTOS。
 */

#ifndef EFW_DS_H
#define EFW_DS_H

#include "efw/core/common.h"
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t *buffer;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t size;
} efw_ringbuf_t;

typedef struct {
    uint8_t *buffer;
    size_t item_size;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t count;
} efw_queue_t;

typedef struct {
    uint8_t *buffer;
    size_t item_size;
    size_t capacity;
    size_t count;
} efw_stack_t;

static inline efw_status_t efw_ringbuf_init(efw_ringbuf_t *rb, void *buffer, size_t capacity) {
    if (!rb || !buffer || capacity == 0u) return EFW_ERR_INVALID;
    rb->buffer = (uint8_t *)buffer;
    rb->capacity = capacity;
    rb->head = 0u;
    rb->tail = 0u;
    rb->size = 0u;
    return EFW_OK;
}

static inline void efw_ringbuf_clear(efw_ringbuf_t *rb) {
    if (!rb) return;
    rb->head = 0u;
    rb->tail = 0u;
    rb->size = 0u;
}

static inline size_t efw_ringbuf_size(const efw_ringbuf_t *rb) { return rb ? rb->size : 0u; }
static inline size_t efw_ringbuf_capacity(const efw_ringbuf_t *rb) { return rb ? rb->capacity : 0u; }
static inline size_t efw_ringbuf_free(const efw_ringbuf_t *rb) { return rb ? (rb->capacity - rb->size) : 0u; }
static inline int efw_ringbuf_empty(const efw_ringbuf_t *rb) { return !rb || rb->size == 0u; }
static inline int efw_ringbuf_full(const efw_ringbuf_t *rb) { return rb && rb->size == rb->capacity; }

static inline efw_status_t efw_ringbuf_push(efw_ringbuf_t *rb, uint8_t value) {
    if (!rb || !rb->buffer || rb->capacity == 0u) return EFW_ERR_INVALID;
    if (rb->size >= rb->capacity) return EFW_ERR_FULL;
    rb->buffer[rb->head] = value;
    rb->head = (rb->head + 1u) % rb->capacity;
    rb->size++;
    return EFW_OK;
}

static inline efw_status_t efw_ringbuf_pop(efw_ringbuf_t *rb, uint8_t *out) {
    if (!rb || !rb->buffer || !out || rb->capacity == 0u) return EFW_ERR_INVALID;
    if (rb->size == 0u) return EFW_ERR_NOT_FOUND;
    *out = rb->buffer[rb->tail];
    rb->tail = (rb->tail + 1u) % rb->capacity;
    rb->size--;
    return EFW_OK;
}

static inline size_t efw_ringbuf_write(efw_ringbuf_t *rb, const void *data, size_t len) {
    const uint8_t *bytes = (const uint8_t *)data;
    size_t written = 0u;
    if (!rb || !bytes) return 0u;
    while (written < len && efw_ringbuf_push(rb, bytes[written]) == EFW_OK) {
        written++;
    }
    return written;
}

static inline size_t efw_ringbuf_read(efw_ringbuf_t *rb, void *out, size_t len) {
    uint8_t *bytes = (uint8_t *)out;
    size_t read = 0u;
    if (!rb || !bytes) return 0u;
    while (read < len && efw_ringbuf_pop(rb, &bytes[read]) == EFW_OK) {
        read++;
    }
    return read;
}

static inline efw_status_t efw_queue_init(efw_queue_t *q, void *buffer, size_t item_size, size_t capacity) {
    if (!q || !buffer || item_size == 0u || capacity == 0u) return EFW_ERR_INVALID;
    q->buffer = (uint8_t *)buffer;
    q->item_size = item_size;
    q->capacity = capacity;
    q->head = 0u;
    q->tail = 0u;
    q->count = 0u;
    return EFW_OK;
}

static inline void efw_queue_clear(efw_queue_t *q) {
    if (!q) return;
    q->head = 0u;
    q->tail = 0u;
    q->count = 0u;
}

static inline size_t efw_queue_count(const efw_queue_t *q) { return q ? q->count : 0u; }
static inline int efw_queue_empty(const efw_queue_t *q) { return !q || q->count == 0u; }
static inline int efw_queue_full(const efw_queue_t *q) { return q && q->count == q->capacity; }

static inline efw_status_t efw_queue_push(efw_queue_t *q, const void *item) {
    if (!q || !q->buffer || !item || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count >= q->capacity) return EFW_ERR_FULL;
    memcpy(q->buffer + (q->head * q->item_size), item, q->item_size);
    q->head = (q->head + 1u) % q->capacity;
    q->count++;
    return EFW_OK;
}

static inline efw_status_t efw_queue_pop(efw_queue_t *q, void *out) {
    if (!q || !q->buffer || !out || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count == 0u) return EFW_ERR_NOT_FOUND;
    memcpy(out, q->buffer + (q->tail * q->item_size), q->item_size);
    q->tail = (q->tail + 1u) % q->capacity;
    q->count--;
    return EFW_OK;
}

static inline efw_status_t efw_queue_peek(const efw_queue_t *q, void *out) {
    if (!q || !q->buffer || !out || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count == 0u) return EFW_ERR_NOT_FOUND;
    memcpy(out, q->buffer + (q->tail * q->item_size), q->item_size);
    return EFW_OK;
}

static inline efw_status_t efw_stack_init(efw_stack_t *s, void *buffer, size_t item_size, size_t capacity) {
    if (!s || !buffer || item_size == 0u || capacity == 0u) return EFW_ERR_INVALID;
    s->buffer = (uint8_t *)buffer;
    s->item_size = item_size;
    s->capacity = capacity;
    s->count = 0u;
    return EFW_OK;
}

static inline void efw_stack_clear(efw_stack_t *s) { if (s) s->count = 0u; }
static inline size_t efw_stack_count(const efw_stack_t *s) { return s ? s->count : 0u; }
static inline int efw_stack_empty(const efw_stack_t *s) { return !s || s->count == 0u; }
static inline int efw_stack_full(const efw_stack_t *s) { return s && s->count == s->capacity; }

static inline efw_status_t efw_stack_push(efw_stack_t *s, const void *item) {
    if (!s || !s->buffer || !item || s->item_size == 0u || s->capacity == 0u) return EFW_ERR_INVALID;
    if (s->count >= s->capacity) return EFW_ERR_FULL;
    memcpy(s->buffer + (s->count * s->item_size), item, s->item_size);
    s->count++;
    return EFW_OK;
}

static inline efw_status_t efw_stack_pop(efw_stack_t *s, void *out) {
    if (!s || !s->buffer || !out || s->item_size == 0u || s->capacity == 0u) return EFW_ERR_INVALID;
    if (s->count == 0u) return EFW_ERR_NOT_FOUND;
    s->count--;
    memcpy(out, s->buffer + (s->count * s->item_size), s->item_size);
    return EFW_OK;
}

static inline efw_status_t efw_stack_peek(const efw_stack_t *s, void *out) {
    if (!s || !s->buffer || !out || s->item_size == 0u || s->capacity == 0u) return EFW_ERR_INVALID;
    if (s->count == 0u) return EFW_ERR_NOT_FOUND;
    memcpy(out, s->buffer + ((s->count - 1u) * s->item_size), s->item_size);
    return EFW_OK;
}

#ifdef __cplusplus
}
#endif

#endif
