import { useEffect, useState } from 'react'
import { App, Avatar, Button, Form, Input, Modal, Upload } from 'antd'
import {
  CalendarOutlined,
  CheckOutlined,
  EditOutlined,
  IdcardOutlined,
  LockOutlined,
  MailOutlined,
  UploadOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'

export default function ProfilePage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const fetchUser = useAuthStore((s) => s.fetchUser)

  const [uploading, setUploading] = useState(false)
  // 昵称编辑态
  const [editingNick, setEditingNick] = useState(false)
  const [nickname, setNickname] = useState('')
  const [savingNick, setSavingNick] = useState(false)
  // 修改密码弹窗
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  const [savingPwd, setSavingPwd] = useState(false)

  useEffect(() => {
    setNickname(user?.nickname || '')
  }, [user?.nickname])

  const displayName = user?.nickname || user?.username || '用户'

  const onSaveNickname = async () => {
    const v = nickname.trim()
    if (!v) {
      message.warning('昵称不能为空')
      return
    }
    setSavingNick(true)
    try {
      await authApi.updateProfile(v)
      await fetchUser()
      setEditingNick(false)
      message.success('昵称已更新')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSavingNick(false)
    }
  }

  const onChangePassword = async (v: {
    oldPassword: string
    newPassword: string
  }) => {
    setSavingPwd(true)
    try {
      await authApi.changePassword(v.oldPassword, v.newPassword)
      message.success('密码修改成功')
      pwdForm.resetFields()
      setPwdOpen(false)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSavingPwd(false)
    }
  }

  const uploadProps = {
    showUploadList: false,
    accept: '.jpg,.jpeg,.png,.webp,.gif',
    beforeUpload: async (file: File) => {
      setUploading(true)
      try {
        await authApi.uploadAvatar(file)
        await fetchUser()
        message.success('头像更新成功')
      } catch (e) {
        message.error((e as Error).message)
      } finally {
        setUploading(false)
      }
      return false
    },
  }

  const infoRows = [
    { icon: <UserOutlined />, label: '账号', value: user?.username || '-' },
    { icon: <MailOutlined />, label: '邮箱', value: user?.email || '未绑定' },
    {
      icon: <CalendarOutlined />,
      label: '注册时间',
      value: user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-',
    },
  ]

  return (
    <div className="fluid-page" style={{ maxWidth: '52rem' }}>
      {/* 炫酷资料卡 */}
      <div className="profile-card">
        <div className="profile-cover" />
        <div className="profile-head">
          <div className="profile-avatar-wrap">
            {user?.avatar ? (
              <AuthenticatedImage src={user.avatar} alt="头像" className="profile-avatar" />
            ) : (
              <Avatar size={104} icon={<UserOutlined />} className="profile-avatar-fallback">
                {displayName[0]?.toUpperCase()}
              </Avatar>
            )}
            <Upload {...uploadProps}>
              <button className="profile-avatar-edit" disabled={uploading} title="更换头像">
                {uploading ? '…' : <UploadOutlined />}
              </button>
            </Upload>
          </div>
          <div className="profile-name">{displayName}</div>
          <div className="profile-sub">@{user?.username}</div>
        </div>

        {/* 信息行 */}
        <div className="profile-body">
          {/* 昵称（可编辑） */}
          <div className="profile-row">
            <span className="profile-row-icon">
              <IdcardOutlined />
            </span>
            <span className="profile-row-label">昵称</span>
            <span className="profile-row-value">
              {editingNick ? (
                <span style={{ display: 'inline-flex', gap: 8, width: '100%' }}>
                  <Input
                    autoFocus
                    value={nickname}
                    onChange={(e) => setNickname(e.target.value)}
                    onPressEnter={onSaveNickname}
                    maxLength={64}
                    placeholder="设置昵称（用于打招呼）"
                  />
                  <Button
                    type="primary"
                    icon={<CheckOutlined />}
                    loading={savingNick}
                    onClick={onSaveNickname}
                  />
                  <Button
                    onClick={() => {
                      setNickname(user?.nickname || '')
                      setEditingNick(false)
                    }}
                  >
                    取消
                  </Button>
                </span>
              ) : (
                <>
                  <span className={user?.nickname ? '' : 'profile-empty'}>
                    {user?.nickname || '未设置'}
                  </span>
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => setEditingNick(true)}
                  >
                    编辑
                  </Button>
                </>
              )}
            </span>
          </div>

          {infoRows.map((r) => (
            <div className="profile-row" key={r.label}>
              <span className="profile-row-icon">{r.icon}</span>
              <span className="profile-row-label">{r.label}</span>
              <span className="profile-row-value">{r.value}</span>
            </div>
          ))}

          {/* 安全 */}
          <div className="profile-row">
            <span className="profile-row-icon">
              <LockOutlined />
            </span>
            <span className="profile-row-label">密码</span>
            <span className="profile-row-value">
              <span className="profile-empty">••••••••</span>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => setPwdOpen(true)}
              >
                修改密码
              </Button>
            </span>
          </div>
        </div>
      </div>

      {/* 修改密码弹窗 */}
      <Modal
        title="修改密码"
        open={pwdOpen}
        onCancel={() => {
          pwdForm.resetFields()
          setPwdOpen(false)
        }}
        onOk={() => pwdForm.submit()}
        confirmLoading={savingPwd}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form
          form={pwdForm}
          layout="vertical"
          onFinish={onChangePassword}
          requiredMark={false}
          style={{ marginTop: 8 }}
        >
          <Form.Item
            name="oldPassword"
            label="原密码"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="原密码" size="large" />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码不能少于 6 位' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="新密码（至少 6 位）"
              size="large"
            />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" size="large" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
