#pragma once

#include <stddef.h>
#include <stdint.h>

typedef struct StorageFile StorageFile;

/* 0 on success, negative on error. */

int storage_mkdir(const char *path);
int storage_open_write(const char *path, StorageFile **out);
int storage_open_read(const char *path, StorageFile **out);
int storage_write(StorageFile *f, const void *data, size_t len);
int storage_read(StorageFile *f, void *data, size_t len, size_t *got);
int storage_seek(StorageFile *f, long offset);
int storage_close(StorageFile *f);

/* Remaining bytes the HAL will still accept (host sim can quota this). */
int64_t storage_free_bytes(void);
