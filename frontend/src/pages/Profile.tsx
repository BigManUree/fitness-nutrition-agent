import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Card, Spin } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile, saveProfile } from '../api/profile';
import { ApiError } from '../api/client';
import ProfileForm from '../components/ProfileForm';
import type { Profile } from '../types/profile';
import PageContainer from '../components/PageContainer';

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
    return (
      <PageContainer title="用户画像">
        <Alert type="error" message="读取画像失败，请稍后重试" />
      </PageContainer>
    );
  }

  return (
    <PageContainer title="用户画像" subtitle="这些信息用于个性化训练与饮食编排，请如实填写" maxWidth={760}>
      <Card>
        {missing && <Alert type="info" message="尚未填写画像，请填写后保存" style={{ marginBottom: 16 }} />}
        <ProfileForm
          initial={data?.profile}
          onSaved={() => navigate('/plan')}
          onSave={(p) => save.mutateAsync(p)}
          saving={save.isPending}
          saveWarning={saveWarning}
        />
      </Card>
    </PageContainer>
  );
}
