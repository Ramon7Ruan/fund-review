#!/bin/sh
# 克隆仓库后跑一次：bash scripts/install-hooks.sh
# 安装后会阻止直接推送到 main。

set -e

root=$(git rev-parse --show-toplevel)
cd "$root"

hook_src="scripts/hooks/pre-push"
hook_dst=".git/hooks/pre-push"

if [ ! -f "$hook_src" ]; then
    echo "找不到 $hook_src，请在仓库根目录运行"
    exit 1
fi

if [ -f "$hook_dst" ] && ! grep -q "禁止直接推送" "$hook_dst" 2>/dev/null; then
    echo "警告：.git/hooks/pre-push 已存在且不是本项目的钩子"
    printf "覆盖它？[y/N] "
    read -r ans
    case "$ans" in
        y|Y) ;;
        *) echo "已取消"; exit 0 ;;
    esac
fi

cp "$hook_src" "$hook_dst"
chmod +x "$hook_dst"

echo "已安装 pre-push 钩子：直接推送 main 会被拒绝。"
echo "验证方式：git checkout main && git push  应当被拦截。"
