import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Form, Input, Typography, message } from 'antd';
import { login } from '../api/auth';
import { isUnauthorized } from '../api/client';
import { useAuth } from '../auth/useAuth';
import AuthShell from '../components/AuthShell';

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    try {
      const r = await login(values.username, values.password);
      setUser(r.username);
      navigate('/plan', { replace: true });
    } catch (err) {
      if (isUnauthorized(err)) message.error('用户名或密码错误');
      else message.error(err instanceof Error ? err.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>
        欢迎回来
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 28 }}>
        登录以继续你的训练计划
      </Typography.Paragraph>

      <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
        <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
          <Input autoFocus placeholder="请输入用户名" size="large" autoComplete="username" />
        </Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
          <Input.Password placeholder="请输入密码" size="large" autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block size="large">
          登录
        </Button>
      </Form>

      <Typography.Paragraph style={{ marginTop: 20, textAlign: 'center', marginBottom: 0 }}>
        没有账号？<Link to="/register">注册新账号</Link>
      </Typography.Paragraph>
    </AuthShell>
  );
}
