import { Alert, Col, Empty, Image, Row, Space, Tag, Typography } from 'antd';
import { SafetyOutlined } from '@ant-design/icons';
import type { Exercise } from '../types/plan';

const { Text, Paragraph } = Typography;

/** 优先取中文列表，回退英文原文；都没有返回 null。 */
function pickList(ex: Exercise, key: keyof Exercise, zhKey: keyof Exercise): string[] | null {
  const zh = ex[zhKey];
  if (Array.isArray(zh) && zh.length > 0) return zh as string[];
  const en = ex[key];
  if (Array.isArray(en) && en.length > 0) return en as string[];
  return null;
}

function pickText(ex: Exercise, key: keyof Exercise, zhKey: keyof Exercise): string | null {
  const zh = ex[zhKey];
  if (typeof zh === 'string' && zh.trim()) return zh;
  const en = ex[key];
  if (typeof en === 'string' && en.trim()) return en;
  return null;
}

/**
 * 单个动作的完整详解：演示图、演示视频、动作简介、分步教学、
 * 常见错误、安全提示、变化动作、别名关键词、渐进负荷。
 * 所有内容来自 MCP（中文译文优先），组件本身不编写动作信息。
 */
export default function ExerciseDetail({ ex }: { ex: Exercise }) {
  const images = ex.image_urls ?? [];
  const videoUrls = (ex.videos ?? [])
    .map((v) => (typeof v === 'string' ? v : v?.url))
    .filter((u): u is string => typeof u === 'string' && u.length > 0);
  const overview = pickText(ex, 'overview', 'overview_zh');
  const instructions = pickList(ex, 'instructions', 'instructions_zh');
  const mistakes = pickList(ex, 'common_mistakes', 'common_mistakes_zh');
  const safety = pickText(ex, 'safety', 'safety_zh');
  const variations = pickList(ex, 'variations', 'variations_zh');
  const keywords = pickList(ex, 'keywords', 'keywords_zh');
  const progression = typeof ex.progression === 'string' ? ex.progression : null;

  const hasAny =
    images.length > 0 ||
    videoUrls.length > 0 ||
    overview ||
    instructions ||
    mistakes ||
    safety ||
    variations ||
    keywords ||
    progression;

  if (!hasAny) return <Empty description="该动作暂无详细资料" image={Empty.PRESENTED_IMAGE_SIMPLE} />;

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {/* 媒体区：左视频、右示范图 */}
      {images.length > 0 || videoUrls.length > 0 ? (
        <Row gutter={16} align="top">
          <Col xs={24} md={12}>
            <Text type="secondary">演示视频</Text>
            {videoUrls.length > 0 ? (
              <video
                src={videoUrls[0]}
                controls
                preload="metadata"
                style={{ width: '100%', maxWidth: 420, marginTop: 6, borderRadius: 8 }}
              />
            ) : (
              <Paragraph type="secondary" style={{ marginTop: 4 }}>
                暂无演示视频
              </Paragraph>
            )}
          </Col>
          <Col xs={24} md={12}>
            <Text type="secondary">示范图</Text>
            {images.length > 0 ? (
              <Image.PreviewGroup>
                <Space size={8} wrap style={{ marginTop: 6 }}>
                  {images.map((src, i) => (
                    <Image
                      key={i}
                      src={src}
                      width={110}
                      height={110}
                      style={{ objectFit: 'cover', borderRadius: 8 }}
                      fallback="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="
                    />
                  ))}
                </Space>
              </Image.PreviewGroup>
            ) : (
              <Paragraph type="secondary" style={{ marginTop: 4 }}>
                暂无示范图
              </Paragraph>
            )}
          </Col>
        </Row>
      ) : null}

      {progression && (
        <div>
          <Text strong>渐进负荷：</Text>
          <Text>{progression}</Text>
        </div>
      )}

      {overview && (
        <div>
          <Text strong>动作简介</Text>
          <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>{overview}</Paragraph>
        </div>
      )}

      {instructions && (
        <div>
          <Text strong>分步教学</Text>
          <ol style={{ margin: '6px 0 0', paddingLeft: 20, lineHeight: 1.9 }}>
            {instructions.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {mistakes && (
        <div>
          <Text strong style={{ color: '#E04F4F' }}>
            常见错误
          </Text>
          <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: '#5A6478', lineHeight: 1.9 }}>
            {mistakes.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {safety && (
        <Alert
          type="warning"
          showIcon
          icon={<SafetyOutlined />}
          message="安全提示"
          description={safety}
        />
      )}

      {variations && (
        <div>
          <Text strong>变化 / 进阶动作：</Text>
          <Space size={[6, 6]} wrap style={{ marginLeft: 4 }}>
            {variations.map((v, i) => (
              <Tag key={i}>{v}</Tag>
            ))}
          </Space>
        </div>
      )}

      {keywords && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          别名 / 关键词：{keywords.join('、')}
        </Text>
      )}
    </Space>
  );
}
