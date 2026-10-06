import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Drawer, Dropdown, Grid, Layout, Menu, Space, Typography } from 'antd';
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
import { palette, spacing } from '../theme/tokens';

const { Sider, Header, Content } = Layout;
const { useBreakpoint } = Grid;

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
        flexShrink: 0,
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: palette.primary,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: palette.white,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        健
      </div>
      {!collapsed && (
        <span style={{ color: palette.white, fontWeight: 600, fontSize: 15, whiteSpace: 'nowrap' }}>
          健身营养 Agent
        </span>
      )}
    </div>
  );
}

interface SideMenuProps {
  selectedKey: string;
  onNavigate: (key: string) => void;
}

/** 侧边菜单本体（固定 Sider 与移动 Drawer 共用）。 */
function SideMenu({ selectedKey, onNavigate }: SideMenuProps) {
  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[selectedKey]}
      items={NAV}
      onClick={({ key }) => onNavigate(key)}
      style={{ borderInlineEnd: 'none', marginTop: spacing.sm }}
    />
  );
}

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const screens = useBreakpoint();
  // lg（992px）以下用抽屉式导航，避免固定 Sider 挤占小屏内容
  const isMobile = !screens.lg;

  // 命中最长前缀，保证子路由也高亮对应菜单
  const selectedKey =
    NAV.map((n) => n.key)
      .filter((k) => (k === '/' ? location.pathname === '/' : location.pathname.startsWith(k)))
      .sort((a, b) => b.length - a.length)[0] ?? '/';

  const go = (key: string) => {
    navigate(key);
    setDrawerOpen(false); // 移动端：选择后自动收起抽屉
  };

  const onLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {!isMobile && (
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          width={224}
          style={{ position: 'sticky', top: 0, height: '100vh' }}
        >
          <BrandMark collapsed={collapsed} />
          <SideMenu selectedKey={selectedKey} onNavigate={go} />
        </Sider>
      )}

      {/* 移动端抽屉导航：无圆角、铺满全高 */}
      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={240}
          styles={{
            body: { padding: 0, background: palette.siderBg },
            header: { display: 'none' },
          }}
        >
          <BrandMark collapsed={false} />
          <SideMenu selectedKey={selectedKey} onNavigate={go} />
        </Drawer>
      )}

      <Layout style={{ minWidth: 0 }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: spacing.base,
            borderBottom: `1px solid ${palette.border}`,
            position: 'sticky',
            top: 0,
            zIndex: 10,
            paddingInline: isMobile ? spacing.base : spacing.xl,
          }}
        >
          <Space
            style={{ color: palette.textSecondary, cursor: 'pointer', fontSize: 16 }}
            onClick={() => (isMobile ? setDrawerOpen(true) : setCollapsed((c) => !c))}
            aria-label={isMobile ? '打开导航菜单' : '折叠导航'}
          >
            {isMobile || collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
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
              {/* 窄屏只保留头像，避免用户名挤占 */}
              {!isMobile && <Typography.Text style={{ color: palette.text }}>{user}</Typography.Text>}
            </Space>
          </Dropdown>
        </Header>

        <Content style={{ padding: isMobile ? spacing.base : spacing.xl }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
