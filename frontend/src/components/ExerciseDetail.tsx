import { Alert, Col, Empty, Image, Row, Space, Tag, Typography } from 'antd';
import { SafetyOutlined } from '@ant-design/icons';
import type { Exercise } from '../types/plan';
import { fontSize, palette } from '../theme/tokens';

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

/** 解析视频字段（可能是字符串或 { url } 对象）。 */
function parseVideoUrl(v: unknown): string | null {
  if (typeof v === 'string') return v;
  if (v && typeof v === 'object' && 'url' in v && typeof v.url === 'string') return v.url;
  return null;
}

// ─── 拆分的叶子组件，降低父组件复杂度 ──────────────────────────

/** 媒体区：左视频、右示范图。 */
function MediaSection({ images, videoUrls }: { images: string[]; videoUrls: string[] }) {
  return (
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
        <Image.PreviewGroup>
          <Space size={8} wrap style={{ marginTop: 6 }}>
            {images.map((src) => (
              <Image
                key={src}
                src={src}
                width={110}
                height={110}
                style={{ objectFit: 'cover', borderRadius: 8 }}
                fallback="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="
              />
            ))}
          </Space>
        </Image.PreviewGroup>
      </Col>
    </Row>
  );
}

/** 有序步骤列表（分步教学）。 */
function StepsList({ steps }: { steps: string[] }) {
  return (
    <ol style={{ margin: '6px 0 0', paddingLeft: 20, lineHeight: 1.9 }}>
      {steps.map((step) => (
        <li key={step}>{step}</li>
      ))}
    </ol>
  );
}

/** 无序错误列表。 */
function MistakesList({ mistakes }: { mistakes: string[] }) {
  return (
    <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: palette.textSecondary, lineHeight: 1.9 }}>
      {mistakes.map((m) => (
        <li key={m}>{m}</li>
      ))}
    </ul>
  );
}

/** 变化动作标签组。 */
function VariationTags({ variations }: { variations: string[] }) {
  return (
    <Space size={[6, 6]} wrap style={{ marginLeft: 4 }}>
      {variations.map((v) => (
        <Tag key={v}>{v}</Tag>
      ))}
    </Space>
  );
}

// ─── 主组件 ──────────────────────────────────────────────────

interface ExerciseContent {
  images: string[];
  videoUrls: string[];
  overview: string | null;
  instructions: string[] | null;
  mistakes: string[] | null;
  safety: string | null;
  variations: string[] | null;
  keywords: string[] | null;
  progression: string | null;
}

/** 从 Exercise 挑选要展示的字段（中文译文优先），与渲染解耦。 */
function selectContent(ex: Exercise): ExerciseContent {
  return {
    images: ex.image_urls ?? [],
    videoUrls: (ex.videos ?? []).map(parseVideoUrl).filter((u): u is string => u !== null),
    overview: pickText(ex, 'overview', 'overview_zh'),
    instructions: pickList(ex, 'instructions', 'instructions_zh'),
    mistakes: pickList(ex, 'common_mistakes', 'common_mistakes_zh'),
    safety: pickText(ex, 'safety', 'safety_zh'),
    variations: pickList(ex, 'variations', 'variations_zh'),
    keywords: pickList(ex, 'keywords', 'keywords_zh'),
    progression: typeof ex.progression === 'string' ? ex.progression : null,
  };
}

/** 是否至少有一项内容可展示。 */
function hasContent(c: ExerciseContent): boolean {
  return Boolean(
    c.images.length ||
      c.videoUrls.length ||
      c.overview ||
      c.instructions ||
      c.mistakes ||
      c.safety ||
      c.variations ||
      c.keywords ||
      c.progression,
  );
}

/** 详解正文：各板块按有无内容条件渲染。 */
function DetailBody({ content }: { content: ExerciseContent }) {
  const { images, videoUrls, overview, instructions, mistakes, safety, variations, keywords, progression } = content;
  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {(images.length > 0 || videoUrls.length > 0) && (
        <MediaSection images={images} videoUrls={videoUrls} />
      )}

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
          <StepsList steps={instructions} />
        </div>
      )}

      {mistakes && (
        <div>
          <Text strong style={{ color: palette.error }}>
            常见错误
          </Text>
          <MistakesList mistakes={mistakes} />
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
          <VariationTags variations={variations} />
        </div>
      )}

      {keywords && (
        <Text type="secondary" style={{ fontSize: fontSize.caption }}>
          别名 / 关键词：{keywords.join('、')}
        </Text>
      )}
    </Space>
  );
}

// ─── 主组件 ──────────────────────────────────────────────────

/**
 * 单个动作的完整详解：演示图、演示视频、动作简介、分步教学、
 * 常见错误、安全提示、变化动作、别名关键词、渐进负荷。
 * 所有内容来自 MCP（中文译文优先），组件本身不编写动作信息。
 */
export default function ExerciseDetail({ ex }: { ex: Exercise }) {
  const content = selectContent(ex);
  if (!hasContent(content)) {
    return <Empty description="该动作暂无详细资料" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  return <DetailBody content={content} />;
}
