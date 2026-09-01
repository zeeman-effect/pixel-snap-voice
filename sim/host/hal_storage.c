#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#else
#include <sys/stat.h>
#define MKDIR(p) mkdir((p), 0755)
#endif

#include "storage.h"

struct StorageFile {
    FILE *fp;
};

static char g_root[512] = ".";
static int64_t g_quota = -1; /* negative = unlimited */
static int64_t g_used;

static void join_path(char *out, size_t n, const char *rel)
{
    if (rel[0] == '\0') {
        snprintf(out, n, "%s", g_root);
        return;
    }
    snprintf(out, n, "%s/%s", g_root, rel);
}

void host_storage_set_root(const char *root)
{
    snprintf(g_root, sizeof(g_root), "%s", root);
    g_used = 0;
}

void host_storage_set_quota(int64_t bytes)
{
    g_quota = bytes;
}

void host_storage_reset_quota(void)
{
    g_quota = -1;
    g_used = 0;
}

int storage_mkdir(const char *path)
{
    char full[768];
    join_path(full, sizeof(full), path);
    if (MKDIR(full) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static int open_mode(const char *path, const char *mode, StorageFile **out)
{
    char full[768];
    StorageFile *f;
    FILE *fp;

    join_path(full, sizeof(full), path);
    fp = fopen(full, mode);
    if (!fp) {
        return -1;
    }
    f = (StorageFile *)calloc(1, sizeof(*f));
    if (!f) {
        fclose(fp);
        return -1;
    }
    f->fp = fp;
    *out = f;
    return 0;
}

int storage_open_write(const char *path, StorageFile **out)
{
    return open_mode(path, "wb+", out);
}

int storage_open_read(const char *path, StorageFile **out)
{
    return open_mode(path, "rb", out);
}

int storage_write(StorageFile *f, const void *data, size_t len)
{
    size_t n;
    if (!f || !f->fp) {
        return -1;
    }
    if (g_quota >= 0 && g_used + (int64_t)len > g_quota) {
        return -1;
    }
    n = fwrite(data, 1, len, f->fp);
    if (n != len) {
        return -1;
    }
    g_used += (int64_t)len;
    return 0;
}

int storage_read(StorageFile *f, void *data, size_t len, size_t *got)
{
    size_t n;
    if (got) {
        *got = 0;
    }
    if (!f || !f->fp || !data) {
        return -1;
    }
    n = fread(data, 1, len, f->fp);
    if (got) {
        *got = n;
    }
    if (n < len && ferror(f->fp)) {
        return -1;
    }
    return 0;
}

int storage_seek(StorageFile *f, long offset)
{
    if (!f || !f->fp) {
        return -1;
    }
    return fseek(f->fp, offset, SEEK_SET) == 0 ? 0 : -1;
}

int storage_close(StorageFile *f)
{
    if (!f) {
        return 0;
    }
    if (f->fp) {
        fclose(f->fp);
    }
    free(f);
    return 0;
}

int64_t storage_free_bytes(void)
{
    if (g_quota < 0) {
        return INT64_C(1) << 40;
    }
    if (g_used >= g_quota) {
        return 0;
    }
    return g_quota - g_used;
}
