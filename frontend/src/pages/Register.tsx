import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { register } from '../api/auth';
import { useAuth } from '../auth/useAuth';

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
    <div style={{ maxWidth: 420, margin: '80px auto' }}>
      <Card title="注册新账号">
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { pattern: /^[A-Za-z0-9_]{3,20}$/, message: '3-20 位字母/数字/下划线' },
            ]}
          >
            <Input autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认密码"
            rules={[{ required: true, message: '请再次输入密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            注册并登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16 }}>
          已有账号？<Link to="/login">去登录</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
