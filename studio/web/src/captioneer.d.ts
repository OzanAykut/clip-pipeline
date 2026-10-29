// remotion-captioneer (MIT) bilesenlerine dogrudan erisim; paketin ana girisi Node kodu (whisper) da yukluyor.
declare module 'captioneer-ui' {
  import type React from 'react';
  export interface CWord { word: string; startMs: number; endMs: number; confidence: number; emphasis?: boolean }
  export interface CSegment { text: string; startMs: number; endMs: number; words: CWord[]; speaker?: string }
  export interface CaptionData { segments: CSegment[]; language: string; durationMs: number }
  export interface CaptionComponentProps {
    captions: CaptionData; style?: string; fontFamily?: string; fontSize?: number; fontColor?: string;
    highlightColor?: string; backgroundColor?: string; position?: 'top' | 'center' | 'bottom'; maxWidth?: number;
    wordsPerLine?: number; useSmartWrap?: boolean; emphasisStyle?: 'scale' | 'color' | 'glow'; emphasisColor?: string;
  }
  export const AnimatedCaptions: React.FC<CaptionComponentProps>;
}
declare module 'captioneer-presets' {
  export interface CaptionPreset {
    name: string; description?: string; style: string; fontFamily?: string; fontSize?: number; fontColor?: string;
    highlightColor?: string; backgroundColor?: string; position?: 'top' | 'center' | 'bottom'; [k: string]: unknown;
  }
  export const presets: Record<string, CaptionPreset>;
  export function getPresetCategories(): Record<string, string[]>;
}
