import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * 单个卡片级错误边界。
 * 组员的 Panel 抛异常时，只有这张卡片变成降级提示，整页仍然可用。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[feature:${this.props.title}] 渲染失败`, error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="card border-red-200">
          <div className="mb-2 text-sm font-medium text-red-700">{this.props.title} 渲染失败</div>
          <p className="text-xs text-ink-500">
            这个功能出错了，其他功能不受影响。错误：{this.state.error.message}
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
