# 工作钟

本机用的上下班打卡与工时记录。零依赖：标准库起 HTTP 服务，数据存在本地 SQLite，不上传。

打开后先打卡进入桌面；工作一段、休息一段都会记下来。日报写完自动保存，年底可导出 Markdown，交给 AI 做年报。

## 快速启动

机器上已装 Python 3 即可。默认地址：[http://127.0.0.1:8765/](http://127.0.0.1:8765/)

**Windows**

双击 `start.bat`。它会在后台启动服务并打开浏览器。若端口已被占用，只会打开已在跑的页面。

`start.bat` 通过 `clock.vbs` 调用 `C:\Program Files\Python312\pythonw.exe`。若本机 Python 不在这个路径，改用下面的命令。

**macOS**

双击 `start.command`。效果和 Windows 一样：后台启动、打开浏览器；端口已被占用则只打开页面。

第一次可能被拦截：右键文件 → 打开。若提示无权限，在终端执行：

```bash
chmod +x start.command
```

脚本会按顺序找 `.venv`、Homebrew、系统自带的 `python3`。Finder 启动时 PATH 很短，不要依赖「终端里能跑的 `python3`」。

**任意系统（终端）**

```bash
python3 app.py --open
```

Windows 上也可以写成 `python app.py --open`。不加 `--open` 只启动服务，不自动开浏览器。再次执行带 `--open` 时，若服务已在跑，只会打开页面。

**Docker**

```bash
docker compose up --build
```

浏览器打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。数据挂在仓库的 `data/` 目录。

## 能做什么

- **上班 / 下班**：上班打卡后才进入桌面；下班会结束当天未收尾的分段。
- **工作 / 休息**：开始工作时可写「正在做什么」；去休息会单独计时。休息也算在打卡时长里，但不计入工作时长。
- **校准时间**：补改当天上班、下班时刻；「重置下班」可把误打的下班撤掉。
- **翻日期**：看前一天、后一天的记录。
- **统计**：今日打卡 / 工作 / 休息，以及本周打卡合计。
- **今日工作**：日报自动保存。
- **导出今年**：下载当年 Markdown（打卡、分段、日报）。

时段风景会按上午 / 中午 / 下午 / 夜里切换。记录只在这台电脑的 SQLite 里。

## 数据与配置

- 数据库：`data/clock.db`（首次启动自动创建）。目录已加入 `.gitignore`。
- 环境变量：`HOST`（默认 `127.0.0.1`）、`PORT`（默认 `8765`）。Docker 镜像里 `HOST=0.0.0.0`，时区 `Asia/Shanghai`。

## 测试

```bash
python test_clock.py
```

通过会打印 `ok`。

## 目录

| 路径 | 作用 |
| --- | --- |
| `app.py` | 服务与打卡逻辑 |
| `static/` | 页面与时段图片 |
| `start.bat` / `clock.vbs` | Windows 一键启动 |
| `start.command` | macOS 一键启动 |
| `compose.yaml` / `Dockerfile` | 容器运行 |
| `test_clock.py` | 测试 |
| `DESIGN.md` | 界面设计约定 |
