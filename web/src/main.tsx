import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { getThemeConfig } from './theme'
import { useThemeStore } from './stores/themeStore'
import './index.css'

function Root() {
  const mode = useThemeStore((state) => state.mode)

  useEffect(() => {
    document.documentElement.dataset.theme = mode
  }, [mode])

  return (
    <React.StrictMode>
      <ConfigProvider locale={zhCN} theme={getThemeConfig(mode)}>
        <AntApp style={{ height: '100%' }}>
          <App />
        </AntApp>
      </ConfigProvider>
    </React.StrictMode>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(<Root />)
