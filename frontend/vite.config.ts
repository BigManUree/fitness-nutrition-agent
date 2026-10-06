import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // 放行 Cloudflare 快速隧道域名（'.' 前缀匹配所有 *.trycloudflare.com 子域）；
    // 否则公网访问会被 Vite 的 DNS 重绑定防护拦截
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 稳定的第三方分包：浏览器可长期缓存，业务 chunk 变更不连带失效
        // 只锁定稳定的基础库；antd 不做整包分包——交给 Rollup 按路由
        // 自动拆分，避免首屏加载仅其他页面用到的组件
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
});
