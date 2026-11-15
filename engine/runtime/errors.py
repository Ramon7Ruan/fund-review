"""插件运行时的异常类型。

所有异常都应携带可读的中文说明，因为它们会直接出现在 /api/plugins 与启动日志里。
"""

from __future__ import annotations


class PluginError(Exception):
    """插件相关错误的基类。"""


class PluginLoadError(PluginError):
    """插件模块导入失败，或模块没有导出合法的 PLUGIN 对象。"""


class PluginContractError(PluginError):
    """插件声明不符合契约（如 id 非法、缺少 run 函数）。"""


class PluginExecutionError(PluginError):
    """插件运行期抛出的异常。框架会捕获并转为可展示的失败结果。"""
