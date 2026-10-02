import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Dropdown, Layout, Menu, Space, Typography } from 'antd';
import {
  AppstoreOutlined,
  CalendarOutlined,
  MessageOutlined,
  IdcardOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/useAuth';
import { palette } from '../theme/tokens';

const { Sider, Header, Content } = Layout;

const NAV = [
  { key: '/', label: '工作台', icon: <AppstoreOutlined /> },
  { key: '/plan', label: '计划生成', icon: <CalendarOutlined /> },
  { key: '/chat', label: '对话调整', icon: <MessageOutlined /> },
  { key: '/profile', label: '用户画像', icon: <IdcardOutlined /> },
];

function BrandMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      style={{
        height: 60,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: collapsed ? '0 20px' : '0 18px',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: `linear-gradient(135deg, ${palette.primary}, #7B93F0)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        健
      </div>
      {!collapsed && (
        <span style={{ color: '#fff', fontWeight: 600, fontSize: 15, whiteSpace: 'nowrap' }}>
          健身营养 Agent
        </span>
      )}
    </div>
  );
}

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // 命中最长前缀，保证子路由也高亮对应菜单
  const selectedKey =
    NAV.map((n) => n.key)
      .filter((k) => (k === '/' ? location.pathname === '/' : location.pathname.startsWith(k)))
      .sort((a, b) => b.length - a.length)[0] ?? '/plan';

  const onLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={224}
        style={{ position: 'sticky', top: 0, height: '100vh' }}
      >
        <BrandMark collapsed={collapsed} />
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={NAV}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 'none', marginTop: 8 }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${palette.border}`,
            position: 'sticky',
            top: 0,
            zIndex: 10,
          }}
        >
          <Space
            style={{ color: palette.textSecondary, cursor: 'pointer', fontSize: 16 }}
            onClick={() => setCollapsed((c) => !c)}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </Space>

          <Dropdown
            menu={{
              items: [
                { key: 'profile', icon: <IdcardOutlined />, label: '用户画像', onClick: () => navigate('/profile') },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: onLogout },
              ],
            }}
            placement="bottomRight"
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar style={{ backgroundColor: palette.primary }}>
                {(user ?? '?').slice(0, 1).toUpperCase()}
              </Avatar>
              <Typography.Text style={{ color: palette.text }}>{user}</Typography.Text>
            </Space>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
