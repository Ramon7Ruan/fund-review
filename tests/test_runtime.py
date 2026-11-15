"""插件运行时的核心测试。

重点验证三件事：
1. 新增目录即被发现，不需要改任何注册文件。
2. 单个插件出错不影响其他插件。
3. 删除目录后重新加载，应用仍然可用（可逆性）。
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from engine.runtime import PluginRegistry
from engine.runtime.errors import PluginExecutionError

PACKAGE = "tmp_plugins"

GOOD_PLUGIN = """
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult

def run(ctx: PluginContext) -> PluginResult:
    return PluginResult(status="ready", data=dict(echo=ctx.month))

PLUGIN = AlgorithmPlugin(id="{id}", title="{title}", run=run, status="ready")
"""

BROKEN_PLUGIN = """
raise RuntimeError("导入即失败")
"""

RAISING_PLUGIN = """
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult

def run(ctx: PluginContext) -> PluginResult:
    raise ValueError("运行期失败")

PLUGIN = AlgorithmPlugin(id="{id}", title="{title}", run=run, status="ready")
"""


def write_plugin(root: Path, name: str, code: str) -> Path:
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "plugin.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return pkg


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pkg_root = tmp_path / PACKAGE
    pkg_root.mkdir(parents=True, exist_ok=True)
    (pkg_root / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield pkg_root
    for name in [m for m in sys.modules if m == PACKAGE or m.startswith(f"{PACKAGE}.")]:
        del sys.modules[name]


def test_discovers_plugins_without_registry_file(sandbox: Path) -> None:
    write_plugin(sandbox, "alpha", GOOD_PLUGIN.format(id="demo.alpha", title="甲"))
    write_plugin(sandbox, "beta", GOOD_PLUGIN.format(id="demo.beta", title="乙"))

    registry = PluginRegistry(PACKAGE)
    registry.load()

    assert sorted(registry.ids()) == ["demo.alpha", "demo.beta"]


def test_broken_plugin_is_isolated(sandbox: Path) -> None:
    write_plugin(sandbox, "alpha", GOOD_PLUGIN.format(id="demo.alpha", title="甲"))
    write_plugin(sandbox, "broken", BROKEN_PLUGIN)

    registry = PluginRegistry(PACKAGE)
    registry.load()

    assert registry.get("demo.alpha") is not None
    broken = [i for i in registry.all() if not i.available]
    assert len(broken) == 1
    assert "导入即失败" in (broken[0].error or "")


def test_template_prefix_is_skipped(sandbox: Path) -> None:
    write_plugin(sandbox, "_template", GOOD_PLUGIN.format(id="demo.tpl", title="模板"))
    registry = PluginRegistry(PACKAGE)
    registry.load()
    assert registry.ids() == []


def test_duplicate_id_keeps_first(sandbox: Path) -> None:
    write_plugin(sandbox, "a_first", GOOD_PLUGIN.format(id="demo.same", title="先"))
    write_plugin(sandbox, "b_second", GOOD_PLUGIN.format(id="demo.same", title="后"))

    registry = PluginRegistry(PACKAGE)
    registry.load()

    assert registry.ids() == ["demo.same"]
    duplicates = [i for i in registry.all() if not i.available]
    assert len(duplicates) == 1
    assert "重复" in (duplicates[0].error or "")


def test_runtime_failure_is_contained(sandbox: Path) -> None:
    write_plugin(sandbox, "boom", RAISING_PLUGIN.format(id="demo.boom", title="炸"))
    write_plugin(sandbox, "ok", GOOD_PLUGIN.format(id="demo.ok", title="好"))

    registry = PluginRegistry(PACKAGE)
    registry.load()

    from engine.runtime.plugin import PluginContext

    with pytest.raises(PluginExecutionError):
        registry.execute("demo.boom", PluginContext(month="2026-10"))

    result, error = registry.execute_safely("demo.boom", PluginContext(month="2026-10"))
    assert result is None
    assert error is not None and "运行期失败" in error

    good = registry.execute("demo.ok", PluginContext(month="2026-10"))
    assert good.data["echo"] == "2026-10"


def test_removing_plugin_is_reversible(sandbox: Path) -> None:
    write_plugin(sandbox, "alpha", GOOD_PLUGIN.format(id="demo.alpha", title="甲"))
    write_plugin(sandbox, "beta", GOOD_PLUGIN.format(id="demo.beta", title="乙"))

    registry = PluginRegistry(PACKAGE)
    registry.load()
    assert len(registry.ids()) == 2

    import shutil

    shutil.rmtree(sandbox / "beta")
    for name in [m for m in sys.modules if m.startswith(f"{PACKAGE}.beta")]:
        del sys.modules[name]
    registry.load()

    assert registry.ids() == ["demo.alpha"]


def test_real_package_loads_builtin_plugins() -> None:
    registry = PluginRegistry()
    registry.load()
    ids = registry.ids()
    assert "returns.interval" in ids
    assert "attribution.brinson" in ids
    assert "screening.anomaly" in ids
    assert all(i.available for i in registry.all())
