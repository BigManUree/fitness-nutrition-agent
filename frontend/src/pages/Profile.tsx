import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Spin, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile, saveProfile } from '../api/profile';
import { ApiError } from '../api/client';
import ProfileForm from '../components/ProfileForm';
import type { Profile } from '../types/profile';

export default function Profile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // 告警独立成 state：开始新保存时立刻清空，避免上一次失败文案挂在表单上
  const [saveWarning, setSaveWarning] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['profile'], queryFn: getProfile });

  const save = useMutation({
    mutationFn: (p: Profile) => saveProfile(p),
    onMutate: () => setSaveWarning(null),
    onSuccess: (resp) => {
      setSaveWarning(resp.indexing_warning ?? null);
      return queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
  });

  const missing = isError && error instanceof ApiError && error.status === 404;

  if (isLoading) return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  if (isError && !missing) {
    return <Alert type="error" message="读取画像失败，请稍后重试" style={{ margin: 40 }} />;
  }

  return (
    <div style={{ maxWidth: 720, margin: '40px auto' }}>
      <Typography.Title level={3}>📋 用户画像</Typography.Title>
      {missing && <Alert type="info" message="尚未填写画像，请填写后保存" style={{ marginBottom: 16 }} />}
      <ProfileForm
        initial={data?.profile}
        onSaved={() => navigate('/plan')}
        onSave={(p) => save.mutateAsync(p)}
        saving={save.isPending}
        saveWarning={saveWarning}
      />
    </div>
  );
}
