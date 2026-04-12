import { useState } from 'react';
import type { Paragraph, Sentence, Word } from '../lib/data';

type Mode = 'original' | 'parallel' | 'detail';

interface Props {
  paragraphs: Paragraph[];
}

export default function ReadingView({ paragraphs }: Props) {
  const [mode, setMode] = useState<Mode>('parallel');

  return (
    <div>
      {/* 模式切换 */}
      <div className="flex justify-center mb-8">
        <div className="inline-flex">
          <button
            className={`mode-btn ${mode === 'original' ? 'active' : ''}`}
            onClick={() => setMode('original')}
          >
            原文
          </button>
          <button
            className={`mode-btn ${mode === 'parallel' ? 'active' : ''}`}
            onClick={() => setMode('parallel')}
          >
            对照
          </button>
          <button
            className={`mode-btn ${mode === 'detail' ? 'active' : ''}`}
            onClick={() => setMode('detail')}
          >
            逐词
          </button>
        </div>
      </div>

      {/* 正文 */}
      <div className="space-y-8">
        {paragraphs.map((para, i) => (
          <ParagraphView key={i} paragraph={para} mode={mode} />
        ))}
      </div>
    </div>
  );
}

function ParagraphView({ paragraph, mode }: { paragraph: Paragraph; mode: Mode }) {
  if (mode === 'original') {
    return <OriginalMode paragraph={paragraph} />;
  }
  if (mode === 'parallel') {
    return <ParallelMode paragraph={paragraph} />;
  }
  return <DetailMode paragraph={paragraph} />;
}

/* ============================================================
   原文模式：纯古文，点击词弹出释义
   ============================================================ */
function OriginalMode({ paragraph }: { paragraph: Paragraph }) {
  return (
    <div className="prose-classical text-xl sm:text-2xl leading-relaxed">
      {paragraph.sentences.map((sentence, i) => (
        <SentenceWithPopover key={i} sentence={sentence} />
      ))}
    </div>
  );
}

/* ============================================================
   对照模式：原文 + 整段翻译
   ============================================================ */
function ParallelMode({ paragraph }: { paragraph: Paragraph }) {
  return (
    <div className="space-y-3">
      <div className="prose-classical text-lg sm:text-xl leading-relaxed">
        {paragraph.original}
      </div>
      {paragraph.translation && (
        <div className="translation-text pl-4 border-l-2 border-border-light">
          {paragraph.translation}
        </div>
      )}
    </div>
  );
}

/* ============================================================
   逐词模式：拼音 + 逐句翻译 + 词释义
   ============================================================ */
function DetailMode({ paragraph }: { paragraph: Paragraph }) {
  return (
    <div className="space-y-6">
      {paragraph.sentences.map((sentence, i) => (
        <div key={i} className="space-y-2">
          {/* 带拼音的原文 */}
          <div className="flex flex-wrap items-end gap-x-0.5 gap-y-4">
            {sentence.words
              .filter(w => w.word.trim() && !isPunctuation(w.word))
              .map((word, j) => (
                <WordWithPinyin key={j} word={word} />
              ))}
          </div>
          {/* 句子翻译 */}
          {sentence.translation && (
            <div className="translation-text text-sm pl-1">
              {sentence.translation}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ============================================================
   单词组件：拼音标注 + 点击弹出释义
   ============================================================ */
function WordWithPinyin({ word }: { word: Word }) {
  const [open, setOpen] = useState(false);

  const typeColor: Record<string, string> = {
    '人名': 'text-cinnabar',
    '地名': 'text-azure',
    '官职': 'text-bamboo',
    '典故': 'text-amber-700',
    '书名': 'text-purple-700',
  };

  const colorClass = typeColor[word.type] || '';

  return (
    <span
      className="relative inline-flex flex-col items-center cursor-pointer group"
      onClick={() => setOpen(!open)}
      onMouseLeave={() => setOpen(false)}
    >
      {/* 拼音 */}
      <span className="pinyin-text mb-0.5 opacity-80 group-hover:opacity-100">
        {word.pinyin}
      </span>
      {/* 汉字 */}
      <span
        className={`prose-classical text-lg sm:text-xl hover:text-cinnabar transition-colors ${colorClass}`}
      >
        {word.word}
      </span>
      {/* 弹窗 */}
      {open && (
        <div className="word-popover">
          <div className="font-semibold text-sm mb-1">
            {word.word}
            <span className="font-normal text-gray-400 ml-2">{word.pinyin}</span>
          </div>
          <div className="text-xs opacity-90">{word.meaning}</div>
          <div className="text-xs opacity-60 mt-1">{word.type}</div>
        </div>
      )}
    </span>
  );
}

/* ============================================================
   原文模式下的可点击句子
   ============================================================ */
function SentenceWithPopover({ sentence }: { sentence: Sentence }) {
  const [activeWord, setActiveWord] = useState<number | null>(null);

  return (
    <span className="inline">
      {sentence.words.map((word, i) => {
        if (isPunctuation(word.word)) {
          return <span key={i} className="prose-classical">{word.word}</span>;
        }
        return (
          <span
            key={i}
            className="relative inline-block cursor-pointer hover:text-cinnabar transition-colors"
            onClick={() => setActiveWord(activeWord === i ? null : i)}
            onMouseLeave={() => setActiveWord(null)}
          >
            {word.word}
            {activeWord === i && (
              <div className="word-popover">
                <div className="font-semibold text-sm mb-1">
                  {word.word}
                  <span className="font-normal text-gray-400 ml-2">{word.pinyin}</span>
                </div>
                <div className="text-xs opacity-90">{word.meaning}</div>
                <div className="text-xs opacity-60 mt-1">{word.type}</div>
              </div>
            )}
          </span>
        );
      })}
    </span>
  );
}

function isPunctuation(char: string): boolean {
  return /^[，。、；：？！""''《》（）【】\s·—…]+$/.test(char);
}
