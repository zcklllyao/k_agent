/**
 * 全局 ErrorBoundary —— 兜底渲染异常,避免白屏。
 *
 * React 组件树任何子组件抛错都会触发,显示错误堆栈 + 重试按钮,
 * 不至于让整个页面变成白屏(白屏几乎无法定位)。
 *
 * 用法:在 App.tsx 顶层包裹整个 Routes。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Result, Typography } from 'antd'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  info: ErrorInfo | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 控制台同时打一份,方便 F12 看完整堆栈
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 渲染失败:', error, info)
    this.setState({ info })
  }

  handleReload = () => {
    this.setState({ error: null, info: null })
    window.location.reload()
  }

  handleClearAndReload = () => {
    try {
      localStorage.clear()
      sessionStorage.clear()
    } catch {
      /* ignore */
    }
    window.location.href = '/login'
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div style={{ minHeight: '100vh', padding: 24, background: '#FAFAFA' }}>
        <Result
          status="error"
          title="页面渲染出错了"
          subTitle="把下面这段错误信息发给开发者会快很多。"
          extra={[
            <Button type="primary" key="reload" onClick={this.handleReload}>
              重新加载
            </Button>,
            <Button key="clear" onClick={this.handleClearAndReload}>
              清缓存并回登录页
            </Button>,
          ]}
        />
        <div
          style={{
            maxWidth: 960,
            margin: '0 auto',
            padding: 16,
            background: '#fff',
            border: '1px solid #eef0f4',
            borderRadius: 12,
          }}
        >
          <Typography.Title level={5} style={{ marginTop: 0 }}>
            错误信息
          </Typography.Title>
          <pre
            style={{
              background: '#1f1f1f',
              color: '#ff6b6b',
              padding: 12,
              borderRadius: 8,
              overflow: 'auto',
              maxHeight: 240,
              fontSize: 12,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
          </pre>
          {this.state.info?.componentStack && (
            <>
              <Typography.Title level={5} style={{ marginTop: 16 }}>
                组件栈
              </Typography.Title>
              <pre
                style={{
                  background: '#fafbfc',
                  color: '#475467',
                  padding: 12,
                  borderRadius: 8,
                  overflow: 'auto',
                  maxHeight: 240,
                  fontSize: 12,
                  lineHeight: 1.6,
                }}
              >
                {this.state.info.componentStack}
              </pre>
            </>
          )}
        </div>
      </div>
    )
  }
}
