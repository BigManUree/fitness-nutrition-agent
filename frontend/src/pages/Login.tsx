import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { login } from '../api/auth';
import { isUnauthorized } from '../api/client';
import { useAuth } from '../auth/useAuth';

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
    <div style={{ maxWidth: 420, margin: '80px auto' }}>
      <Card title="登录 健身营养 Agent">
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16 }}>
          没有账号？<Link to="/register">注册新账号</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
