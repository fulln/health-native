# HealthNative

**Apple 健康原生快捷指令 + Mac 本地健康看板。**

在 iPhone 上导出记录到自己的 iCloud，再在 Mac 浏览器中查看步数、活动能量、心率、静息心率、体重和睡眠。个人记录由本机读取；公开演示使用合成数据。

[快捷指令下载与安装](https://shortcuts.fulleen.com/) · [示例看板](https://shortcuts.fulleen.com/dashboard.html) · [GitHub](https://github.com/fulln/health-native)

![合成示例看板](docs/images/healthnative-demo.jpg)

## 本地运行

需要 **Python 3.9 或更新版本**，无需安装 Python 包、npm 或数据库。

```sh
git clone https://github.com/fulln/health-native.git
cd health-native
python3 -m health_native
```

打开终端显示的地址：<http://127.0.0.1:8764/dashboard.html>。按 `Ctrl+C` 停止。

默认读取当前用户的 iCloud「快捷指令」目录：

```text
~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents
```

同时兼容 `~/Library/Mobile Documents/com~apple~CloudDocs/HealthNative`。只读取 `health-native-YYYY-MM-DD_HHmmss.json` 和 `health-native-latest.json`，测试文件不会参与统计。

自定义目录可重复指定，多个目录一起合并：

```sh
python3 -m health_native --data-dir "/path/to/health-json" --data-dir "/another/folder"
```

默认按北京时间归档。可指定 IANA 时区与本地端口：

```sh
python3 -m health_native --timezone Europe/London --port 8765
```

## 能做什么

- **读取原生导出**：兼容 HealthNativeDated 的列式批量 JSON 与原生 records 格式。
- **合并多个文件**：重复快照不重复累计，同一个样本的较新修订覆盖旧值。
- **按自然日看趋势**：7 / 30 / 90 天，日期空缺保留为空，六类指标可切换。
- **分别标注记录日期**：活动与次晨睡眠不会被强行归成同一天；普通心率均值和静息心率分别展示。
- **查看来源与质量**：显示读取目录、文件数、重复样本数、部分记录和睡眠阶段。
- **本地只读**：只监听 `127.0.0.1`，不会修改 iCloud 文件或向公共网站上传健康记录。

首次在 iPhone 上添加并运行快捷指令，需要允许六类健康记录的只读权限及保存到自己的 iCloud。安装步骤、每天 9 点自动化和实体操作按钮设置见下载页。

## 数据口径

- 步数与活动能量按样本区间整理。同源区间相交时保守采用非重叠记录，并标为部分数据；跨来源区间重叠时选择覆盖时间最多的一种来源，避免把手机和手表重复相加。
- 心率记录均值来自同一主来源的样本，不替代静息心率。体重选取当天最后一次有效测量，并统一为 kg。
- 睡眠先组成连续 session，再按最终醒来日期归档。统计 asleep 区间并集，排除 InBed / Awake；未分层记录与详细阶段不重复累计。互相矛盾的详细阶段交集归为未分层，并标注部分数据。
- `capture_scope=daily` 的活动只采用导出前一天完整日期；睡眠采用本次导出当天醒来的 session。`export_date` 是采集启动时间，不能当作 iCloud 上传完成时间。
- 无记录为缺失，不补零，不从历史体重或普通心率推算其他指标。

iCloud 仍在同步或文件尚未下载时，看板会显示文件状态。请先在「文件」或 Finder 中确认导出文件已同步，再刷新。本项目不绕过 iCloud 的同步限制，也不直接调用 Mac 上的 HealthKit。

单文件最多 20MB / 10 万条样本；单轮最多读取最近 1000 个生产文件、100 万条候选样本。超限会显示提示。

## 公开演示与自己的数据

公共下载站仅部署 `web/`，展示 `web/demo.json` 中的合成数据；没有健康数据接收接口。

本地看板从同源 `/api/health` 读取本机聚合结果。`?demo=1` 可以在本地明确切换到合成演示模式。示例数据与真实数据不会悄悄互相替换。

## 项目结构

```text
health_native/       本地只读服务、格式校验与聚合
web/                 下载页、SVG 看板与合成演示
web/downloads/       可添加到 iPhone 的已签名快捷指令
shortcuts/           可审阅的快捷指令工作流 plist 源码
tests/               临时目录中的合成数据与 HTTP 边界测试
docs/                使用与实现说明
```

下载包 basename 保持 `HealthNativeDated.shortcut`，避免改变安装时的指令名称。源码 plist 可供审阅；签名包需要在 iPhone 的「快捷指令」中添加和编辑。

## 验证

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q health_native
node --check web/dashboard.js
node --check web/landing.js
```

Node.js 只用于开发时检查脚本语法，运行看板不需要它。测试与演示均使用合成数据。个人导出文件、凭证和本机验收产物不进入仓库。

## 开源

MIT License。欢迎提交格式兼容、日期归档或图表可用性方面的改进。报告问题时请提供去除个人来源名称的合成最小样例，避免上传自己的健康记录。
