import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Form, Input, Typography, message } from 'antd';
import { register } from '../api/auth';
import { useAuth } from '../auth/useAuth';
import AuthShell from '../components/AuthShell';

export default function Register() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: {
    username: string;
    password: string;
    confirm: string;
  }) => {
    if (values.password !== values.confirm) {
      message.error('两次输入的密码不一致');
      return;
    }
    setSubmitting(true);
    try {
      const r = await register(values.username, values.password);
      setUser(r.username);
      navigate('/plan', { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注册失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>
        创建账号
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 28 }}>
        几步即可生成专属训练与饮食方案
      </Typography.Paragraph>

      <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
        <Form.Item
          name="username"
          label="用户名"
          rules={[
            { required: true, message: '请输入用户名' },
            { pattern: /^[A-Za-z0-9_]{3,20}$/, message: '3-20 位字母/数字/下划线' },
          ]}
        >
          <Input autoFocus placeholder="3-20 位字母/数字/下划线" size="large" autoComplete="username" />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[
            { required: true, message: '请输入密码' },
            { min: 6, message: '密码至少 6 位' },
          ]}
        >
          <Input.Password placeholder="至少 6 位" size="large" autoComplete="new-password" />
        </Form.Item>
        <Form.Item name="confirm" label="确认密码" rules={[{ required: true, message: '请再次输入密码' }]}>
          <Input.Password placeholder="再次输入密码" size="large" autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block size="large">
          注册并登录
        </Button>
      </Form>

      <Typography.Paragraph style={{ marginTop: 20, textAlign: 'center', marginBottom: 0 }}>
        已有账号？<Link to="/login">去登录</Link>
      </Typography.Paragraph>
    </AuthShell>
  );
}
