#include "wifi_share.h"

#include <dirent.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "board.h"
#include "config.h"
#include "esp_log.h"
#include "sdkconfig.h"
#include "storage_sd.h"

#if CONFIG_PSV_WIFI_SHARE

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

static const char *TAG = "psv.share";

#define SHARE_IP_A 192
#define SHARE_IP_B 168
#define SHARE_IP_C 4
#define SHARE_IP_D 1
#define TX_POWER_QDBM 40 /* 10 dBm; units are 0.25 dBm */
#define FILE_CHUNK 1024
#define DNS_PORT 53

static httpd_handle_t s_httpd;
static esp_netif_t *s_ap;
static int s_wifi_ready;
static int s_active;
static int s_dns_sock = -1;
static TaskHandle_t s_dns_task;
static uint8_t s_chunk[FILE_CHUNK];

static int is_wav_name(const char *name)
{
    size_t n;
    if (!name) {
        return 0;
    }
    n = strlen(name);
    if (n < 5) {
        return 0;
    }
    {
        const char *ext = name + n - 4;
        return ext[0] == '.' &&
               (ext[1] == 'w' || ext[1] == 'W') &&
               (ext[2] == 'a' || ext[2] == 'A') &&
               (ext[3] == 'v' || ext[3] == 'V');
    }
}

static int name_ok(const char *name)
{
    size_t i;
    if (!name || name[0] == '\0' || name[0] == '.') {
        return 0;
    }
    for (i = 0; name[i]; i++) {
        char c = name[i];
        int ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                 (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.';
        if (!ok) {
            return 0;
        }
    }
    return is_wav_name(name);
}

static const char *leaf_of(const char *uri)
{
    const char *slash;
    if (!uri) {
        return "";
    }
    slash = strrchr(uri, '/');
    return slash ? slash + 1 : uri;
}

static int is_index_uri(const char *uri)
{
    return !uri || uri[0] == '\0' || strcmp(uri, "/") == 0 ||
           strcmp(uri, "/recordings") == 0 || strcmp(uri, "/recordings/") == 0;
}

static int is_captive_uri(const char *uri)
{
    static const char *const probes[] = {
        "/hotspot-detect.html",
        "/generate_204",
        "/gen_204",
        "/ncsi.txt",
        "/connecttest.txt",
        "/canonical.html",
        "/success.txt",
        "/redirect",
        "/library/test/success.html",
        NULL,
    };
    int i;
    if (!uri) {
        return 0;
    }
    for (i = 0; probes[i]; i++) {
        if (strcmp(uri, probes[i]) == 0) {
            return 1;
        }
    }
    return 0;
}

static void dav_headers(httpd_req_t *req)
{
    httpd_resp_set_hdr(req, "DAV", "1");
    httpd_resp_set_hdr(req, "MS-Author-Via", "DAV");
    httpd_resp_set_hdr(req, "Allow", "GET, HEAD, OPTIONS, PROPFIND");
}

static esp_err_t send_index(httpd_req_t *req)
{
    DIR *d;
    struct dirent *e;
    char dirpath[256];
    const char *mount = storage_sd_mount_point();

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    snprintf(
        (char *)s_chunk,
        sizeof(s_chunk),
        "<!doctype html><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Pixel Snap Voice</title>"
        "<style>body{font-family:sans-serif;margin:1.2rem;max-width:40rem}"
        "li{margin:.8rem 0}audio{width:100%%}</style>"
        "<h1>Recordings</h1><p>Join <b>%s</b>, then this page. "
        "USB still works. Double-press the button to stop Wi-Fi.</p><ul>",
        CONFIG_PSV_WIFI_SSID
    );
    httpd_resp_sendstr_chunk(req, (char *)s_chunk);

    if (mount) {
        snprintf(dirpath, sizeof(dirpath), "%s/%s", mount, PSV_RECORDINGS_DIR);
        d = opendir(dirpath);
        if (d) {
            while ((e = readdir(d)) != NULL) {
                if (!name_ok(e->d_name)) {
                    continue;
                }
                snprintf(
                    (char *)s_chunk,
                    sizeof(s_chunk),
                    "<li><div>%s</div>"
                    "<audio controls preload=\"none\" src=\"/recordings/%s\"></audio>"
                    "<div><a href=\"/recordings/%s\" download>Download</a></div></li>",
                    e->d_name,
                    e->d_name,
                    e->d_name
                );
                httpd_resp_sendstr_chunk(req, (char *)s_chunk);
            }
            closedir(d);
        }
    }
    httpd_resp_sendstr_chunk(req, "</ul>");
    return httpd_resp_sendstr_chunk(req, NULL);
}

static esp_err_t send_wav(httpd_req_t *req, const char *name)
{
    char path[PSV_MAX_PATH + 64];
    const char *mount = storage_sd_mount_point();
    FILE *fp;
    struct stat st;
    size_t n;
    char disp[128];

    if (!mount || !name_ok(name)) {
        httpd_resp_set_status(req, "404 Not Found");
        return httpd_resp_send(req, "not found", HTTPD_RESP_USE_STRLEN);
    }
    snprintf(path, sizeof(path), "%s/%s/%s", mount, PSV_RECORDINGS_DIR, name);
    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode)) {
        httpd_resp_set_status(req, "404 Not Found");
        return httpd_resp_send(req, "not found", HTTPD_RESP_USE_STRLEN);
    }
    fp = fopen(path, "rb");
    if (!fp) {
        httpd_resp_set_status(req, "404 Not Found");
        return httpd_resp_send(req, "not found", HTTPD_RESP_USE_STRLEN);
    }
    httpd_resp_set_type(req, "audio/wav");
    snprintf(disp, sizeof(disp), "inline; filename=\"%s\"", name);
    httpd_resp_set_hdr(req, "Content-Disposition", disp);
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    if (req->method == HTTP_HEAD) {
        fclose(fp);
        return httpd_resp_send(req, NULL, 0);
    }
    while ((n = fread(s_chunk, 1, sizeof(s_chunk), fp)) > 0) {
        if (httpd_resp_send_chunk(req, (char *)s_chunk, n) != ESP_OK) {
            fclose(fp);
            httpd_resp_sendstr_chunk(req, NULL);
            return ESP_FAIL;
        }
    }
    fclose(fp);
    return httpd_resp_send_chunk(req, NULL, 0);
}

static int href_is_dir(const char *href)
{
    size_t n = strlen(href);
    return n == 0 || href[n - 1] == '/';
}

static void prop_response(char *out, size_t n, const char *href, int collection, size_t nbytes)
{
    if (collection) {
        snprintf(
            out,
            n,
            "<D:response><D:href>%s</D:href><D:propstat><D:prop>"
            "<D:resourcetype><D:collection/></D:resourcetype>"
            "</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>",
            href
        );
        return;
    }
    snprintf(
        out,
        n,
        "<D:response><D:href>%s</D:href><D:propstat><D:prop>"
        "<D:resourcetype/>"
        "<D:getcontentlength>%u</D:getcontentlength>"
        "<D:getcontenttype>audio/wav</D:getcontenttype>"
        "</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>",
        href,
        (unsigned)nbytes
    );
}

static esp_err_t send_propfind(httpd_req_t *req)
{
    const char *uri = req->uri;
    const char *mount = storage_sd_mount_point();
    DIR *d;
    struct dirent *e;
    char dirpath[256];
    char path[PSV_MAX_PATH + 64];
    char xml[512];
    struct stat st;

    dav_headers(req);
    httpd_resp_set_status(req, "207 Multi-Status");
    httpd_resp_set_type(req, "application/xml; charset=utf-8");
    httpd_resp_sendstr_chunk(req, "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                                  "<D:multistatus xmlns:D=\"DAV:\">");

    if (is_index_uri(uri) || strcmp(uri, "/") == 0) {
        prop_response(xml, sizeof(xml), "/", 1, 0);
        httpd_resp_sendstr_chunk(req, xml);
        prop_response(xml, sizeof(xml), "/recordings/", 1, 0);
        httpd_resp_sendstr_chunk(req, xml);
    }
    if (is_index_uri(uri) || strncmp(uri, "/recordings", 11) == 0) {
        if (!href_is_dir(uri) && name_ok(leaf_of(uri)) && mount) {
            snprintf(path, sizeof(path), "%s/%s/%s", mount, PSV_RECORDINGS_DIR, leaf_of(uri));
            if (stat(path, &st) == 0) {
                snprintf((char *)s_chunk, sizeof(s_chunk), "/recordings/%s", leaf_of(uri));
                prop_response(xml, sizeof(xml), (char *)s_chunk, 0, (size_t)st.st_size);
                httpd_resp_sendstr_chunk(req, xml);
            }
        } else if (mount) {
            snprintf(dirpath, sizeof(dirpath), "%s/%s", mount, PSV_RECORDINGS_DIR);
            d = opendir(dirpath);
            if (d) {
                while ((e = readdir(d)) != NULL) {
                    if (!name_ok(e->d_name)) {
                        continue;
                    }
                    snprintf(path, sizeof(path), "%s/%s/%s", mount, PSV_RECORDINGS_DIR, e->d_name);
                    if (stat(path, &st) != 0) {
                        continue;
                    }
                    snprintf((char *)s_chunk, sizeof(s_chunk), "/recordings/%s", e->d_name);
                    prop_response(xml, sizeof(xml), (char *)s_chunk, 0, (size_t)st.st_size);
                    httpd_resp_sendstr_chunk(req, xml);
                }
                closedir(d);
            }
        }
    }
    httpd_resp_sendstr_chunk(req, "</D:multistatus>");
    return httpd_resp_sendstr_chunk(req, NULL);
}

static esp_err_t share_handler(httpd_req_t *req)
{
    const char *uri = req->uri ? req->uri : "/";
    const char *q = strchr(uri, '?');
    char path[128];
    size_t n;

    n = q ? (size_t)(q - uri) : strlen(uri);
    if (n >= sizeof(path)) {
        n = sizeof(path) - 1;
    }
    memcpy(path, uri, n);
    path[n] = '\0';

    if (req->method == HTTP_OPTIONS) {
        dav_headers(req);
        return httpd_resp_send(req, NULL, 0);
    }
    if (req->method == HTTP_PUT || req->method == HTTP_DELETE) {
        httpd_resp_set_status(req, "403 Forbidden");
        return httpd_resp_send(req, "read-only", HTTPD_RESP_USE_STRLEN);
    }
    if (req->method == HTTP_PROPFIND) {
        return send_propfind(req);
    }
    if (req->method != HTTP_GET && req->method != HTTP_HEAD) {
        httpd_resp_set_status(req, "405 Method Not Allowed");
        dav_headers(req);
        return httpd_resp_send(req, NULL, 0);
    }
    if (is_index_uri(path) || is_captive_uri(path)) {
        if (req->method == HTTP_HEAD) {
            httpd_resp_set_type(req, "text/html; charset=utf-8");
            return httpd_resp_send(req, NULL, 0);
        }
        return send_index(req);
    }
    if (strncmp(path, "/recordings/", 12) == 0) {
        return send_wav(req, path + 12);
    }
    httpd_resp_set_status(req, "404 Not Found");
    return httpd_resp_send(req, "not found", HTTPD_RESP_USE_STRLEN);
}

static void register_uri(httpd_handle_t srv, const char *uri, httpd_method_t method)
{
    httpd_uri_t u = {
        .uri = uri,
        .method = method,
        .handler = share_handler,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(srv, &u);
}

static void dns_task(void *arg)
{
    uint8_t buf[512];
    struct sockaddr_in from;
    socklen_t fromlen;
    int sock = s_dns_sock;
    (void)arg;

    while (sock >= 0 && s_dns_sock == sock) {
        fromlen = sizeof(from);
        int n = recvfrom(sock, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fromlen);
        if (s_dns_sock != sock) {
            break;
        }
        if (n < 12) {
            continue;
        }
        /* One A answer: copy the query, set QR+AA, ANCOUNT=1, append A 192.168.4.1. */
        uint16_t qd = ((uint16_t)buf[4] << 8) | buf[5];
        if (qd != 1) {
            continue;
        }
        int qend = 12;
        while (qend < n && buf[qend] != 0) {
            qend += 1 + buf[qend];
            if (qend >= n) {
                qend = -1;
                break;
            }
        }
        if (qend < 0 || qend + 5 > n) {
            continue;
        }
        qend += 5; /* 0 + QTYPE + QCLASS */
        if (qend + 16 > (int)sizeof(buf)) {
            continue;
        }
        buf[2] = 0x84; /* QR, AA */
        buf[3] = 0x00;
        buf[6] = 0x00;
        buf[7] = 0x01; /* ANCOUNT */
        buf[8] = 0x00;
        buf[9] = 0x00;
        buf[10] = 0x00;
        buf[11] = 0x00;
        buf[qend + 0] = 0xc0;
        buf[qend + 1] = 0x0c;
        buf[qend + 2] = 0x00;
        buf[qend + 3] = 0x01; /* A */
        buf[qend + 4] = 0x00;
        buf[qend + 5] = 0x01; /* IN */
        buf[qend + 6] = 0x00;
        buf[qend + 7] = 0x00;
        buf[qend + 8] = 0x00;
        buf[qend + 9] = 0x1e; /* TTL 30s */
        buf[qend + 10] = 0x00;
        buf[qend + 11] = 0x04;
        buf[qend + 12] = SHARE_IP_A;
        buf[qend + 13] = SHARE_IP_B;
        buf[qend + 14] = SHARE_IP_C;
        buf[qend + 15] = SHARE_IP_D;
        sendto(sock, buf, qend + 16, 0, (struct sockaddr *)&from, fromlen);
    }
    vTaskDelete(NULL);
}

static esp_err_t dns_start(void)
{
    struct sockaddr_in addr = {0};
    s_dns_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (s_dns_sock < 0) {
        return ESP_FAIL;
    }
    addr.sin_family = AF_INET;
    addr.sin_port = htons(DNS_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(s_dns_sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(s_dns_sock);
        s_dns_sock = -1;
        return ESP_FAIL;
    }
    if (xTaskCreate(dns_task, "psv_dns", 3072, NULL, 5, &s_dns_task) != pdPASS) {
        close(s_dns_sock);
        s_dns_sock = -1;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

static void dns_stop(void)
{
    int sock = s_dns_sock;
    s_dns_sock = -1;
    if (sock >= 0) {
        shutdown(sock, SHUT_RDWR);
        close(sock);
    }
    s_dns_task = NULL;
}

static esp_err_t http_start(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    static const httpd_method_t methods[] = {
        HTTP_GET,
        HTTP_HEAD,
        HTTP_OPTIONS,
        HTTP_PROPFIND,
        HTTP_PUT,
        HTTP_DELETE,
    };
    size_t i;
    cfg.server_port = 80;
    cfg.lru_purge_enable = true;
    cfg.max_open_sockets = 4;
    cfg.max_uri_handlers = 16;
    cfg.stack_size = 8192;
    cfg.uri_match_fn = httpd_uri_match_wildcard;
    if (httpd_start(&s_httpd, &cfg) != ESP_OK) {
        s_httpd = NULL;
        return ESP_FAIL;
    }
    for (i = 0; i < sizeof(methods) / sizeof(methods[0]); i++) {
        register_uri(s_httpd, "/", methods[i]);
        register_uri(s_httpd, "/*", methods[i]);
    }
    return ESP_OK;
}

static void http_stop(void)
{
    if (s_httpd) {
        httpd_stop(s_httpd);
        s_httpd = NULL;
    }
}

esp_err_t wifi_share_start(void)
{
    wifi_config_t ap = {0};
    esp_err_t err;

    if (s_active) {
        return ESP_OK;
    }

    err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }
    if (!s_ap) {
        s_ap = esp_netif_create_default_wifi_ap();
        if (!s_ap) {
            return ESP_ERR_NO_MEM;
        }
    }
    if (!s_wifi_ready) {
        wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
        err = esp_wifi_init(&init);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "wifi init: %s", esp_err_to_name(err));
            return err;
        }
        s_wifi_ready = 1;
    }

    strncpy((char *)ap.ap.ssid, CONFIG_PSV_WIFI_SSID, sizeof(ap.ap.ssid) - 1);
    strncpy((char *)ap.ap.password, CONFIG_PSV_WIFI_PASS, sizeof(ap.ap.password) - 1);
    ap.ap.ssid_len = strlen(CONFIG_PSV_WIFI_SSID);
    ap.ap.channel = 1;
    ap.ap.max_connection = 2;
    ap.ap.authmode = WIFI_AUTH_WPA2_PSK;
    if (strlen(CONFIG_PSV_WIFI_PASS) < 8) {
        ESP_LOGE(TAG, "WPA2 password is under 8 characters");
        return ESP_ERR_INVALID_ARG;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    err = esp_wifi_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "wifi start: %s", esp_err_to_name(err));
        return err;
    }
    (void)esp_wifi_set_max_tx_power(TX_POWER_QDBM);
    (void)esp_wifi_set_ps(WIFI_PS_NONE);

    err = http_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "httpd start failed");
        esp_wifi_stop();
        return err;
    }
    err = dns_start();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "captive DNS failed; open http://192.168.4.1 by hand");
    }

    s_active = 1;
    ESP_LOGI(
        TAG,
        "share AP '%s' at http://192.168.4.1 (TX ~10 dBm). Mate the IPEX pigtail on the custom board.",
        CONFIG_PSV_WIFI_SSID
    );
    return ESP_OK;
}

void wifi_share_stop(void)
{
    if (!s_active && !s_httpd && s_dns_sock < 0) {
        return;
    }
    http_stop();
    dns_stop();
    if (s_wifi_ready) {
        (void)esp_wifi_stop();
    }
    s_active = 0;
    ESP_LOGI(TAG, "share off");
}

int wifi_share_active(void)
{
    return s_active;
}

#else /* !CONFIG_PSV_WIFI_SHARE */

esp_err_t wifi_share_start(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

void wifi_share_stop(void)
{
}

int wifi_share_active(void)
{
    return 0;
}

#endif
