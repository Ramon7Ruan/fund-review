#!/usr/bin/env bash
# 扩展性验收脚本（AC1 / AC2）
#
# 验证一件事：新增一个功能只需要新增文件，不需要修改任何已存在的文件。
#
# 步骤：
#   1. 复制示例插件（后端 + 前端）到一个临时名字
#   2. 改掉插件 id，避免与示例冲突
#   3. 确认后端运行时可发现它
#   4. 确认 git 变更里只有新增文件（没有修改任何已有文件）
#   5. 删除后确认插件消失（可逆性）
#
# 用法：bash scripts/verify-extensibility.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BACK_SRC="engine/plugins/momentum_summary"
BACK_DST="engine/plugins/zz_verify_ext"
FRONT_SRC="web/src/features/momentum-summary"
FRONT_DST="web/src/features/zz-verify-ext"
PY="${PY:-python3}"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

cleanup() {
  rm -rf "$BACK_DST" "$FRONT_DST"
}
trap cleanup EXIT

echo "== 1. 清理可能残留的临时目录 =="
cleanup

echo "== 2. 复制示例插件（后端 + 前端） =="
cp -R "$BACK_SRC" "$BACK_DST"
cp -R "$FRONT_SRC" "$FRONT_DST"

echo "== 3. 只改插件 id，其余不动 =="
"$PY" - "$BACK_DST/plugin.py" "$FRONT_DST/manifest.ts" <<'PYTHON'
import sys
from pathlib import Path

back, front = Path(sys.argv[1]), Path(sys.argv[2])

text = back.read_text(encoding="utf-8")
text = text.replace('id="example.momentum_summary"', 'id="verify.temp"')
back.write_text(text, encoding="utf-8")

text = front.read_text(encoding="utf-8")
text = text.replace('"example.momentum_summary"', '"verify.temp"')
text = text.replace('"涨跌天数分布（示例）"', '"扩展性验证"')
front.write_text(text, encoding="utf-8")
PYTHON

echo "== 4. 后端运行时是否自动发现（未修改任何注册文件） =="
"$PY" - <<'PYTHON'
from engine.runtime import PluginRegistry

registry = PluginRegistry()
registry.load()
ids = registry.ids()
assert "verify.temp" in ids, f"新插件未被发现，当前插件：{ids}"
assert "example.momentum_summary" in ids, "原有插件丢失"
print("   发现插件：", ", ".join(sorted(ids)))
PYTHON

echo "== 5. git 变更是否只有新增文件 =="
MODIFIED="$(git status --porcelain | grep -E '^( M|M |MM| D|D )' || true)"
if [ -n "$MODIFIED" ]; then
  echo "   失败：以下已存在文件被修改"
  echo "$MODIFIED"
  exit 1
fi
UNTRACKED="$(git status --porcelain | grep -c '^??' || true)"
echo "   未跟踪路径数：$UNTRACKED（预期为 2，即两个新目录）"
if [ "$UNTRACKED" -lt 2 ]; then
  echo "   失败：没有看到新增目录"
  exit 1
fi

echo "== 6. 删除后是否可逆 =="
cleanup
"$PY" - <<'PYTHON'
from engine.runtime import PluginRegistry

registry = PluginRegistry()
registry.load()
ids = registry.ids()
assert "verify.temp" not in ids, "删除目录后插件仍然存在，说明存在隐式缓存"
assert "example.momentum_summary" in ids, "删除临时插件后影响了原有插件"
print("   删除后插件：", ", ".join(sorted(ids)))
PYTHON

echo
echo "扩展性验收通过：新增功能未修改任何已存在文件，删除后亦可逆。"
