# 实现约定

产品：HealthNative。公开下载页 + 只在本机读取 iCloud 的健康记录看板。公开演示使用明确标注的合成数据；个人记录不进入仓库或公共服务器。

无需第三方运行依赖。Python 3.9+ 标准库服务，`python3 -m health_native`，仅绑定 127.0.0.1，默认端口 8764；前端为原生 HTML/CSS/JS 和 SVG。

目录所有权：后端 `health_native/`、Python 测试 `tests/test_*.py`；前端 `web/dashboard.html`、`web/dashboard.css`、`web/dashboard.js`、`web/demo.json`；父代理负责下载首页、文档、仓库、部署和平台发布。

## 读取

默认读取用户自己的 `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents`，兼容 `~/Library/Mobile Documents/com~apple~CloudDocs/HealthNative`。允许命令行重复指定 `--data-dir`，不允许通过 HTTP 参数指定任意文件路径。只读取原生导出生产文件；不读取旧 HealthExport。多 JSON 必须合并去重，不能只读最后一个或重复累计多次快照。数据缺失为 null，不补零；跨午夜睡眠按醒来日期归档；静息心率不使用普通心率均值冒充。

## API 契约

`GET /api/health`，返回完整可用日序列，日期升序。无数据也是同一结构，days 为空。

```json
{
  "mode": "local",
  "generated_at": "2026-10-27T12:00:00+08:00",
  "source": {
    "label": "iCloud · 快捷指令",
    "directories": [],
    "files_read": 0,
    "files_skipped": 0,
    "latest_export": null,
    "warnings": []
  },
  "counts": {"unique_samples": 0, "duplicate_samples": 0},
  "days": [{
    "date": "2026-10-26",
    "steps": null,
    "active_kcal": null,
    "heart_rate_avg_bpm": null,
    "resting_bpm": null,
    "weight_kg": null,
    "sleep_minutes": null,
    "sleep_stages": null,
    "sources": {},
    "partial_metrics": []
  }]
}
```

`sleep_stages` 非空时键为 `core`、`deep`、`rem`、`asleep`（分钟）；sources 为指标字段到来源字符串的映射。source.warnings 是字符串数组，不含原始记录正文。

## 前端

本地服务 `/dashboard.html` 默认请求同源 `/api/health`；公共域名直接读 `demo.json`，或 `?demo=1` 强制示例，醒目标注。没有数据时提供路径/刷新指引，不静默冒充示例或出现假健康数值。不向公共服务器上传用户记录。

首屏显示模式、最新记录日期与数据来源状态，再显示步数/活动能量/静息心率/睡眠等关键指标。范围 7/30/90 天，折线或柱状 SVG 呈现真实缺口，指标可切换。按日查看、来源与数据质量放次层。不做诊断或医学建议。键盘可用，390px 手机和桌面可读。

公开截图强制使用示例数据。完整个人目录只在本地服务中显示；公开文档用 ~ 或泛化路径。
