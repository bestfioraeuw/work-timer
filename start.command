#!/bin/sh
# Finder 双击：后台启动并打开浏览器。终端里也可跑。
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1

pause() {
  echo "按回车关闭。"
  read -r _
}

pick_python() {
  for c in \
    .venv/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3
  do
    if [ -x "$c" ]; then
      echo "$c"
      return 0
    fi
  done
  command -v python3 2>/dev/null
}

PY=$(pick_python) || {
  echo "需要 Python 3。可用 Homebrew：brew install python" >&2
  pause
  exit 1
}

if ! "$PY" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
  echo "找到的 Python 不能用：$PY" >&2
  echo "请安装 Python 3（brew install python），然后重试。" >&2
  pause
  exit 1
fi

nohup "$PY" app.py --open >/dev/null 2>&1 &
