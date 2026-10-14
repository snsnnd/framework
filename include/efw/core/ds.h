/**
 * @file    ds.h
 * @brief   EFW 基础数据结构：字节环形缓冲区、固定长度队列、固定长度栈
 *
 * 所有结构都由调用方提供存储空间，不使用动态内存，不依赖 OS，适合裸机/RTOS。
 */

#ifndef EFW_DS_H
#define EFW_DS_H
// 数据结构模块，该模块的.c和.h合并为单一.h文件

#include "efw/core/common.h"
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

// size_t（unsigned int）表示任何对象在内存中的最大可能大小，等价于sizeof（）返回的类型

typedef struct {
    /** 用户提供的字节存储区；框架不负责分配或释放。 */
    uint8_t *buffer;
    /** 存储区总容量。head/tail 都按该容量回绕。 */
    size_t capacity; 
    /** 下一个写入位置。 */
    size_t head;
    /** 下一个读取位置。 */
    size_t tail;
    /** 当前存储的字节数，取值范围为 [0, capacity]。 */
    size_t size;
} efw_ringbuf_t;  // 环形缓冲区

typedef struct {
    /** 用户提供的连续存储区，大小至少为 item_size * capacity。 */
    uint8_t *buffer;
    /** 每个队列元素的固定字节数。 */
    size_t item_size;
    /** 最多可存储的元素数。 */
    size_t capacity;
    /** 下一个写入元素的槽位。 */
    size_t head;
    /** 下一个读取元素的槽位。 */
    size_t tail;
    /** 当前元素数，先进先出。 */
    size_t count;
} efw_queue_t;  // 队列

typedef struct {
    /** 用户提供的连续存储区，大小至少为 item_size * capacity。 */
    uint8_t *buffer;
    /** 每个栈元素的固定字节数。 */
    size_t item_size;
    /** 最多可存储的元素数。 */
    size_t capacity;
    /** 当前元素数；最后一个元素位于 count - 1。 */
    size_t count;
} efw_stack_t;  // 栈

/** 初始化字节环形缓冲区；不会清零用户 buffer。 */
static inline efw_status_t efw_ringbuf_init(efw_ringbuf_t *rb, void *buffer, size_t capacity) {
    if (!rb || !buffer || capacity == 0u) return EFW_ERR_INVALID; // 返回参数无效
    rb->buffer = (uint8_t *)buffer; // 把用户的buffer传入缓冲区
    rb->capacity = capacity;
    rb->head = 0u;
    rb->tail = 0u;
    rb->size = 0u;
    return EFW_OK;
}

/** 清空环形缓冲区的逻辑内容，不擦除底层字节。 */
static inline void efw_ringbuf_clear(efw_ringbuf_t *rb) {
    if (!rb) return; // 该函数返回为void
    rb->head = 0u;
    rb->tail = 0u;
    rb->size = 0u;
}

// 返回缓冲区当前字节大小
static inline size_t efw_ringbuf_size(const efw_ringbuf_t *rb) { return rb ? rb->size : 0u; }
// 返回缓冲区总容量
static inline size_t efw_ringbuf_capacity(const efw_ringbuf_t *rb) { return rb ? rb->capacity : 0u; }
// 返回缓冲区当前剩余的可用空闲空间
static inline size_t efw_ringbuf_free(const efw_ringbuf_t *rb) { return rb ? (rb->capacity - rb->size) : 0u; }
// 返回缓冲区是否为空
static inline bool efw_ringbuf_empty(const efw_ringbuf_t *rb) { return !rb || rb->size == 0u; }
// 返回缓冲区是否为满
static inline bool efw_ringbuf_full(const efw_ringbuf_t *rb) { return rb && rb->size == rb->capacity; }

/** 写入一个字节，操作首索引；满时返回 EFW_ERR_FULL，不覆盖旧数据。 */
static inline efw_status_t efw_ringbuf_push(efw_ringbuf_t* rb, uint8_t value) {
    if (!rb || !rb->buffer || rb->capacity == 0u) return EFW_ERR_INVALID; // 传入参数无效
    if (rb->size >= rb->capacity) return EFW_ERR_FULL;                    // 缓冲区已满
    rb->buffer[rb->head] = value;                                         // 将数据写入写索引位置

    rb->head = (rb->head + 1u) % rb->capacity;                            // 更新写索引，循环回绕
    // 当 `head` 走到数组最后一个位置 `capacity‑1`，+1 （无符号）之后变成 capacity，要重新跳回下标 0，实现环形。
    /*
        假设大小为4   
        1. head = 0 → (0+1)%4 = 1
        2. head = 1 → (1+1)%4 = 2
        3. head = 2 → (2+1)%4 = 3
        4. head = 3 → (3+1)%4 = 0
    */

    rb->size++;                                                           // 有效数据个数加1
    return EFW_OK;
}

/** 读取并移除一个字节，操作尾索引；空时返回 EFW_ERR_NOT_FOUND。 */
static inline efw_status_t efw_ringbuf_pop(efw_ringbuf_t *rb, uint8_t *out) {
    if (!rb || !rb->buffer || !out || rb->capacity == 0u) return EFW_ERR_INVALID; 
    if (rb->size == 0u) return EFW_ERR_NOT_FOUND;
    *out = rb->buffer[rb->tail];
    rb->tail = (rb->tail + 1u) % rb->capacity;
    rb->size--;
    return EFW_OK;
}

/** 尽可能写入一段字节，返回实际写入长度；空间不足时只写剩余空间。 */
static inline size_t efw_ringbuf_write(efw_ringbuf_t* rb, const void* data, size_t len) {
    const uint8_t* bytes = (const uint8_t*)data;      // 转换为字节指针，用于按字节拷贝
    if (!rb || !bytes || !rb->buffer) return 0u;       // 参数非法，直接返回写入0字节
    size_t avail = rb->capacity - rb->size;            // 缓冲区空闲字节数
    if (len > avail) len = avail;                      // 截断写入长度，不超过空闲空间
    if (len == 0u) return 0u;                          // 无数据需要写入，直接返回

    size_t to_end = rb->capacity - rb->head;           // 写索引到数组末尾剩余字节数
    if (len <= to_end) {                               // 长度够直接写入
        memcpy(rb->buffer + rb->head, bytes, len);
    }
    else {                                             // 长度不够
        memcpy(rb->buffer + rb->head, bytes, to_end); // 先拷贝到数组尾部
        memcpy(rb->buffer, bytes + to_end, len - to_end); // 剩余数据从数组头部开始拷贝
    }
    rb->head = (rb->head + len) % rb->capacity;        // 更新写索引，批量偏移并循环回绕
    rb->size += len;                                   // 增加有效数据计数
    return len;
}


/** 尽可能读出一段字节，返回实际读出长度；数据不足时只读现有数据。 */
static inline size_t efw_ringbuf_read(efw_ringbuf_t *rb, void *out, size_t len) {
    uint8_t *bytes = (uint8_t *)out;
    if (!rb || !bytes || !rb->buffer) return 0u;
    if (len > rb->size) len = rb->size;
    if (len == 0u) return 0u;
    size_t to_end = rb->capacity - rb->tail;
    if (len <= to_end) {
        memcpy(bytes, rb->buffer + rb->tail, len);
    } else {
        memcpy(bytes, rb->buffer + rb->tail, to_end);
        memcpy(bytes + to_end, rb->buffer, len - to_end);
    }
    rb->tail = (rb->tail + len) % rb->capacity;
    rb->size -= len;
    return len;
}

/** 初始化固定元素队列；底层存储由调用方提供。 */
static inline efw_status_t efw_queue_init(efw_queue_t *q, void *buffer, size_t item_size, size_t capacity) {
    if (!q || !buffer || item_size == 0u || capacity == 0u) return EFW_ERR_INVALID;
    q->buffer = (uint8_t *)buffer;      // 提供的缓冲区区域
    q->item_size = item_size;           // 该队列元素的大小
    q->capacity = capacity;             // 容量
    q->head = 0u;
    q->tail = 0u;
    q->count = 0u;
    return EFW_OK;
}

/** 清空队列逻辑内容，不擦除底层存储。 */
static inline void efw_queue_clear(efw_queue_t *q) {
    if (!q) return;
    q->head = 0u;
    q->tail = 0u;
    q->count = 0u;
}

// 返回队列当前元素数量
static inline size_t efw_queue_count(const efw_queue_t *q) { return q ? q->count : 0u; }
// 是否空
static inline bool efw_queue_empty(const efw_queue_t *q) { return !q || q->count == 0u; }
// 是否满
static inline bool efw_queue_full(const efw_queue_t *q) { return q && q->count == q->capacity; }

/** 入队一个元素；队列满时不修改状态。 */
static inline efw_status_t efw_queue_push(efw_queue_t *q, const void *item) {
    if (!q || !q->buffer || !item || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count >= q->capacity) return EFW_ERR_FULL;
    memcpy(q->buffer + (q->head * q->item_size), item, q->item_size); // 将待入队元素拷贝到写索引对应的缓存字节位置
    q->head = (q->head + 1u) % q->capacity;
    q->count++;
    return EFW_OK;
}

/** 出队一个元素；元素按先进先出顺序复制到 out。 */
static inline efw_status_t efw_queue_pop(efw_queue_t *q, void *out) {
    if (!q || !q->buffer || !out || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count == 0u) return EFW_ERR_NOT_FOUND;
    memcpy(out, q->buffer + (q->tail * q->item_size), q->item_size);
    q->tail = (q->tail + 1u) % q->capacity;
    q->count--;
    return EFW_OK;
}

/** 查看队首元素但不移动 tail。 */
static inline efw_status_t efw_queue_peek(const efw_queue_t *q, void *out) {
    if (!q || !q->buffer || !out || q->item_size == 0u || q->capacity == 0u) return EFW_ERR_INVALID;
    if (q->count == 0u) return EFW_ERR_NOT_FOUND;
    memcpy(out, q->buffer + (q->tail * q->item_size), q->item_size);
    return EFW_OK;
}

/** 初始化固定元素栈；栈顶是最后一次 push 的元素。 */
static inline efw_status_t efw_stack_init(efw_stack_t *s, void *buffer, size_t item_size, size_t capacity) {
    if (!s || !buffer || item_size == 0u || capacity == 0u) return EFW_ERR_INVALID;
    s->buffer = (uint8_t *)buffer;
    s->item_size = item_size;
    s->capacity = capacity;
    s->count = 0u;
    return EFW_OK;
}

/** 清空栈逻辑内容，不擦除底层存储。 */
static inline void efw_stack_clear(efw_stack_t *s) { if (s) s->count = 0u; }
static inline size_t efw_stack_count(const efw_stack_t *s) { return s ? s->count : 0u; }
static inline int efw_stack_empty(const efw_stack_t *s) { return !s || s->count == 0u; }
static inline int efw_stack_full(const efw_stack_t *s) { return s && s->count == s->capacity; }

/** 入栈一个元素；栈满时不修改状态。 */
static inline efw_status_t efw_stack_push(efw_stack_t *s, const void *item) {
    if (!s || !s->buffer || !item || s->item_size == 0u || s->capacity == 0u) return EFW_ERR_INVALID;
    if (s->count >= s->capacity) return EFW_ERR_FULL;
    memcpy(s->buffer + (s->count * s->item_size), item, s->item_size);
    s->count++;
    return EFW_OK;
}

/** 弹出栈顶元素；栈空时返回 EFW_ERR_NOT_FOUND。 */
static inline efw_status_t efw_stack_pop(efw_stack_t *s, void *out) {
    if (!s || !s->buffer || !out || s->item_size == 0u || s->capacity == 0u) return EFW_ERR_INVALID;
    if (s->count == 0u) return EFW_ERR_NOT_FOUND;
    s->count--;
    memcpy(out, s->buffer + (s->count * s->item_size), s->item_size);
    return EFW_OK;
}

/** 查看栈顶元素但不减少 count。 */
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
