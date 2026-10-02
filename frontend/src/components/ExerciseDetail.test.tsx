import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ExerciseDetail from './ExerciseDetail';
import type { Exercise } from '../types/plan';

const ENRICHED: Exercise = {
  name: 'Barbell Bench Press',
  name_zh: '杠铃卧推',
  image_urls: ['https://example.com/bench/0.jpg'],
  videos: [{ url: 'https://example.com/bench.mp4' }],
  overview_zh: '杠铃卧推是练胸的核心复合动作。',
  instructions_zh: ['平躺于凳上', '握杆下放至胸部', '发力推回起始位'],
  form_tips_zh: ['肩部收紧下沉', '双脚踩实地面'],
  common_mistakes_zh: ['杠铃弹胸'],
  safety_zh: '大重量时务必有保护者。',
  variations_zh: ['上斜卧推', '哑铃卧推'],
  keywords_zh: ['卧推', 'Bench'],
  progression: '每周加重 2.5-5%',
};

describe('ExerciseDetail', () => {
  it('renders all MCP-enriched fields: media, overview, steps, safety, variations', () => {
    render(<ExerciseDetail ex={ENRICHED} />);

    // 媒体：视频地址与示范图
    const video = screen.getByText('', { selector: 'video' }) as HTMLVideoElement;
    expect(video).toHaveAttribute('src', 'https://example.com/bench.mp4');
    expect(document.querySelector('img.ant-image-img')).toHaveAttribute(
      'src',
      'https://example.com/bench/0.jpg',
    );

    expect(screen.getByText('杠铃卧推是练胸的核心复合动作。')).toBeInTheDocument();
    expect(screen.getByText('平躺于凳上')).toBeInTheDocument();
    expect(screen.getByText('杠铃弹胸')).toBeInTheDocument();
    expect(screen.getByText('大重量时务必有保护者。')).toBeInTheDocument();
    expect(screen.getByText('上斜卧推')).toBeInTheDocument();
    expect(screen.getByText(/卧推、Bench/)).toBeInTheDocument();
    expect(screen.getByText(/每周加重 2.5-5%/)).toBeInTheDocument();
  });

  it('falls back to English fields when no translation exists', () => {
    render(
      <ExerciseDetail
        ex={{ name: 'Squat', overview: 'A fundamental lower body lift.' }}
      />,
    );
    expect(screen.getByText('A fundamental lower body lift.')).toBeInTheDocument();
  });
});
