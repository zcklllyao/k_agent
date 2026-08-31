import { useEffect, useState } from 'react'
import { Button, Checkbox, Form, Input, Tabs, message } from 'antd'
import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import BeianFooter from '@/components/BeianFooter'

interface FormValues {
  email: string
  password: string
}

const LS_REMEMBER = 'k-agent_remember'

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const [tab, setTab] = useState('login')
  const [loading, setLoading] = useState(false)
  const [loginForm] = Form.useForm()
  const [rememberAccount, setRememberAccount] = useState(true)
  const [rememberPassword, setRememberPassword] = useState(false)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_REMEMBER)
      if (!raw) return
      const saved = JSON.parse(raw) as { email?: string; password?: string }
      if (saved.email) {
        loginForm.setFieldsValue({ email: saved.email, password: saved.password ?? '' })
        setRememberAccount(true)
        setRememberPassword(!!saved.password)
      }
    } catch {
      // 回填失败忽略
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onLogin = async (v: FormValues) => {
    setLoading(true)
    try {
      await login(v.email.trim(), v.password)
      if (rememberAccount) {
        localStorage.setItem(
          LS_REMEMBER,
          JSON.stringify({
            email: v.email.trim(),
            password: rememberPassword ? v.password : undefined,
          }),
        )
      } else {
        localStorage.removeItem(LS_REMEMBER)
      }
      message.success('登录成功')
      const redirect = searchParams.get('redirect')
      navigate(redirect || '/', { replace: true })
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const onRegister = async (v: FormValues) => {
    setLoading(true)
    try {
      await register(v.email.trim(), v.password)
      message.success('注册成功，请登录')
      setTab('login')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const renderForm = (
    onFinish: (v: FormValues) => void,
    submitText: string,
    isLogin: boolean,
  ) => (
    <Form
      form={isLogin ? loginForm : undefined}
      layout="vertical"
      onFinish={onFinish}
      disabled={loading}
      requiredMark={false}
      size="large"
    >
      <Form.Item
        name="email"
        validateTrigger="onBlur"
        rules={[
          { required: true, message: '请输入邮箱' },
          { type: 'email', message: '邮箱格式不正确' },
        ]}
      >
        <Input prefix={<MailOutlined />} placeholder="邮箱" autoComplete="email" allowClear />
      </Form.Item>
      <Form.Item
        name="password"
        rules={[
          { required: true, message: '请输入密码' },
          { min: 6, message: '密码不能少于 6 位' },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder="密码（至少 6 位）"
          autoComplete={isLogin ? 'current-password' : 'new-password'}
        />
      </Form.Item>
      {!isLogin && (
        <Form.Item
          name="confirm"
          dependencies={['password']}
          rules={[
            { required: true, message: '请再次输入密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次输入的密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="确认密码"
            autoComplete="new-password"
          />
        </Form.Item>
      )}
      {isLogin && (
        <div className="login2-remember">
          <Checkbox
            checked={rememberAccount}
            onChange={(e) => {
              setRememberAccount(e.target.checked)
              if (!e.target.checked) setRememberPassword(false)
            }}
          >
            记住账号
          </Checkbox>
          <Checkbox
            checked={rememberPassword}
            disabled={!rememberAccount}
            onChange={(e) => setRememberPassword(e.target.checked)}
          >
            记住密码
          </Checkbox>
        </div>
      )}
      <Form.Item style={{ marginBottom: 0, marginTop: 4 }}>
        <Button
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loading}
          style={{ height: 46, fontSize: 16, fontWeight: 600 }}
        >
          {submitText}
        </Button>
      </Form.Item>
    </Form>
  )

  return (
    <div className="applogin">
      <div className="applogin-bg" />

      <div className="applogin-layout">
        <section className="applogin-story" aria-label="k-agent 产品介绍">
          <div className="applogin-story__eyebrow">
            <span aria-hidden="true" className="applogin-story__mark">K</span>
            <span>k-agent / personal knowledge cockpit</span>
          </div>
          <h2>
            把散落的资料
            <br />
            <em>变成可用的判断。</em>
          </h2>
          <p className="applogin-story__intro">
            一个会读文档、记住上下文，也能替你完成研究的个人 AI 工作台。
          </p>
          <div className="applogin-signal" aria-label="产品能力">
            <div className="applogin-signal__line" />
            <div className="applogin-signal__row">
              <span className="applogin-signal__index">01</span>
              <strong>文档</strong>
              <span>归档、检索、带引用回答</span>
            </div>
            <div className="applogin-signal__row">
              <span className="applogin-signal__index">02</span>
              <strong>记忆</strong>
              <span>让每次对话都接得上</span>
            </div>
            <div className="applogin-signal__row">
              <span className="applogin-signal__index">03</span>
              <strong>Agent</strong>
              <span>把问题拆开，交给工具完成</span>
            </div>
          </div>
          <div className="applogin-story__note">
            <span className="applogin-story__dot" />
            你的资料留在自己的空间里
          </div>
        </section>

        <div className="applogin-box">
          <div aria-label="k-agent" className="applogin-logo">K</div>
          <h1 className="applogin-title">k-agent</h1>
          <p className="applogin-sub">
            {tab === 'login' ? '登录，继续你的知识工作' : '创建账号，开启你的 AI 工作台'}
          </p>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            centered
            items={[
              { key: 'login', label: '登录', children: renderForm(onLogin, '登 录', true) },
              {
                key: 'register',
                label: '注册',
                children: renderForm(onRegister, '注 册', false),
              },
            ]}
          />
          <div className="applogin-foot">个人 AI 知识库与记忆助手</div>
        </div>
      </div>
      <div style={{ position: 'fixed', bottom: 14, left: 0, right: 0, zIndex: 2 }}>
        <BeianFooter />
      </div>
    </div>
  )
}
