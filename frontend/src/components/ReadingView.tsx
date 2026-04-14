import { useState, useRef, useEffect } from "react";
import type { HighlightKind, Paragraph, Sentence, Word } from "../lib/types";

type Mode = "original" | "parallel" | "detail";

interface Props {
  paragraphs: Paragraph[];
}

const HIGHLIGHT_STORAGE_KEY = "gwgz_highlight_on";

/** 重点字类别的中文标签（popover 徽章用） */
const HIGHLIGHT_LABEL: Record<HighlightKind, string> = {
  ancient_today: "古今异义",
  loan: "通假字",
  polyphone: "多音字",
  rare: "罕用义",
  fixed: "固定结构",
};

function hlClass(word: Word, on: boolean): string {
  if (!on || !word.highlight) return "";
  return `hl-${word.highlight}`;
}

export default function ReadingView({ paragraphs }: Props) {
  const [mode, setMode] = useState<Mode>("parallel");
  // 默认开启；从 localStorage 读上次偏好
  const [highlightOn, setHighlightOn] = useState<boolean>(true);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(HIGHLIGHT_STORAGE_KEY);
      if (saved === "0") setHighlightOn(false);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleHighlight = () => {
    setHighlightOn((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(HIGHLIGHT_STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  return (
    <div>
      {/* 顶部工具栏：模式切换 + 重点字开关 */}
      <div className="flex flex-wrap items-center justify-center gap-3 mb-8">
        <div className="inline-flex">
          <button
            className={`mode-btn ${mode === "original" ? "active" : ""}`}
            onClick={() => setMode("original")}
          >
            原文
          </button>
          <button
            className={`mode-btn ${mode === "parallel" ? "active" : ""}`}
            onClick={() => setMode("parallel")}
          >
            对照
          </button>
          <button
            className={`mode-btn ${mode === "detail" ? "active" : ""}`}
            onClick={() => setMode("detail")}
          >
            逐词
          </button>
        </div>

        <button
          type="button"
          className={`highlight-toggle ${highlightOn ? "active" : ""}`}
          onClick={toggleHighlight}
          aria-pressed={highlightOn}
          title="切换通假/多音/古今异义/罕用义/固定结构的底色标记"
        >
          <span className="dot" />
          重点字 {highlightOn ? "开" : "关"}
        </button>
      </div>

      {/* 正文 */}
      <div className="space-y-8">
        {paragraphs.map((para, i) => (
          <ParagraphView
            key={i}
            paragraph={para}
            mode={mode}
            highlightOn={highlightOn}
          />
        ))}
      </div>
    </div>
  );
}

function ParagraphView({
  paragraph,
  mode,
  highlightOn,
}: {
  paragraph: Paragraph;
  mode: Mode;
  highlightOn: boolean;
}) {
  if (mode === "original") {
    return <OriginalMode paragraph={paragraph} highlightOn={highlightOn} />;
  }
  if (mode === "parallel") {
    return <ParallelMode paragraph={paragraph} highlightOn={highlightOn} />;
  }
  // 逐词模式不加底色（已拆开展示，加底色反而视觉过载）
  return <DetailMode paragraph={paragraph} />;
}

/* ============================================================
   原文模式：纯古文，点击词弹出释义
   ============================================================ */
function OriginalMode({
  paragraph,
  highlightOn,
}: {
  paragraph: Paragraph;
  highlightOn: boolean;
}) {
  return (
    <div className="prose-classical text-xl sm:text-2xl leading-relaxed">
      {paragraph.sentences.map((sentence, i) => (
        <SentenceWithPopover
          key={i}
          sentence={sentence}
          highlightOn={highlightOn}
        />
      ))}
    </div>
  );
}

/* ============================================================
   对照模式：原文（可点击词查释义） + 整段翻译
   ============================================================ */
function ParallelMode({
  paragraph,
  highlightOn,
}: {
  paragraph: Paragraph;
  highlightOn: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="prose-classical text-lg sm:text-xl leading-relaxed">
        {paragraph.sentences.map((sentence, i) => (
          <SentenceWithPopover
            key={i}
            sentence={sentence}
            highlightOn={highlightOn}
          />
        ))}
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
              .filter((w) => w.word.trim() && !isPunctuation(w.word))
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
   单词组件：拼音标注 + 点击弹出释义（逐词模式）
   ============================================================ */
function WordWithPinyin({ word }: { word: Word }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  const typeColor: Record<string, string> = {
    人名: "text-cinnabar",
    地名: "text-azure",
    官职: "text-bamboo",
    典故: "text-amber-700",
    书名: "text-purple-700",
  };

  const colorClass = typeColor[word.type] || "";

  return (
    <span
      ref={ref}
      className="relative inline-flex flex-col items-center cursor-pointer group"
      onClick={() => setOpen(!open)}
      onMouseLeave={() => setOpen(false)}
    >
      {/* 拼音 */}
      <span className="pinyin-text mb-0.5 opacity-80 group-hover:opacity-100 transition-opacity">
        {word.pinyin}
      </span>
      {/* 汉字 */}
      <span
        className={`prose-classical text-lg sm:text-xl transition-all duration-150 group-hover:text-cinnabar group-hover:scale-110 ${colorClass}`}
      >
        {word.word}
      </span>
      {/* 悬停下划线指示 */}
      <span className="block w-0 h-[1.5px] bg-cinnabar transition-all duration-200 group-hover:w-full mt-0.5 rounded-full" />
      {/* 弹窗 */}
      {open && <WordPopover word={word} parentRef={ref} />}
    </span>
  );
}

/* ============================================================
   原文/对照模式下的可点击句子
   按 sentence.original 顺序对齐词与标点（words 数组本身不含标点）
   ============================================================ */
function SentenceWithPopover({
  sentence,
  highlightOn,
}: {
  sentence: Sentence;
  highlightOn: boolean;
}) {
  const [activeWord, setActiveWord] = useState<number | null>(null);

  const tokens = alignWordsWithText(sentence.original, sentence.words);

  return (
    <span className="inline">
      {tokens.map((tok, i) => {
        if (tok.kind === "text") {
          return (
            <span key={i} className="prose-classical">
              {tok.value}
            </span>
          );
        }
        return (
          <WordInSentence
            key={i}
            word={tok.word}
            highlightOn={highlightOn}
            isActive={activeWord === i}
            onToggle={() => setActiveWord(activeWord === i ? null : i)}
            onLeave={() => setActiveWord(null)}
          />
        );
      })}
    </span>
  );
}

/**
 * 按原文顺序把 words 与未标注字符（标点/空白）对齐。
 * 处理 words 丢失某字符或顺序不匹配的容错。
 */
type AlignedToken =
  | { kind: "word"; word: Word }
  | { kind: "text"; value: string };

function alignWordsWithText(original: string, words: Word[]): AlignedToken[] {
  const result: AlignedToken[] = [];
  let idx = 0;
  let wIdx = 0;
  let textBuf = "";

  const flushText = () => {
    if (textBuf) {
      result.push({ kind: "text", value: textBuf });
      textBuf = "";
    }
  };

  while (idx < original.length) {
    const next = words[wIdx];
    if (next && next.word && original.startsWith(next.word, idx)) {
      flushText();
      result.push({ kind: "word", word: next });
      idx += next.word.length;
      wIdx += 1;
    } else {
      textBuf += original[idx];
      idx += 1;
    }
  }
  flushText();
  return result;
}

/* ============================================================
   句中单词（原文/对照模式用）
   ============================================================ */
function WordInSentence({
  word,
  highlightOn,
  isActive,
  onToggle,
  onLeave,
}: {
  word: Word;
  highlightOn: boolean;
  isActive: boolean;
  onToggle: () => void;
  onLeave: () => void;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const highlightCls = hlClass(word, highlightOn);

  return (
    <span
      ref={ref}
      className={`word-clickable relative inline-block cursor-pointer ${highlightCls}`}
      onClick={onToggle}
      onMouseLeave={onLeave}
    >
      {word.word}
      {isActive && <WordPopover word={word} parentRef={ref} />}
    </span>
  );
}

/* ============================================================
   通用弹窗组件 — 自动调整位置避免溢出
   ============================================================ */
function WordPopover({
  word,
  parentRef,
}: {
  word: Word;
  parentRef: React.RefObject<HTMLSpanElement | null>;
}) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [align, setAlign] = useState<"center" | "left" | "right">("center");

  useEffect(() => {
    const el = popoverRef.current;
    const parent = parentRef.current;
    if (!el || !parent) return;

    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;

    // 检测溢出并调整对齐
    if (rect.left < 8) {
      setAlign("left");
    } else if (rect.right > vw - 8) {
      setAlign("right");
    } else {
      setAlign("center");
    }
  }, [parentRef]);

  const alignClass =
    align === "left"
      ? "left-0 translate-x-0"
      : align === "right"
        ? "right-0 translate-x-0"
        : "left-1/2 -translate-x-1/2";

  const arrowClass =
    align === "left"
      ? "left-3"
      : align === "right"
        ? "right-3"
        : "left-1/2 -translate-x-1/2";

  const hlLabel = word.highlight ? HIGHLIGHT_LABEL[word.highlight] : null;

  return (
    <div ref={popoverRef} className={`word-popover-auto ${alignClass}`}>
      {/* 箭头 */}
      <span
        className={`absolute bottom-full ${arrowClass} border-[6px] border-transparent border-b-[var(--color-ink)]`}
      />
      <div className="font-semibold text-sm mb-1">
        {word.word}
        <span className="font-normal text-gray-400 ml-2">{word.pinyin}</span>
      </div>
      <div className="text-xs opacity-90">{word.meaning}</div>
      <div className="text-xs opacity-60 mt-1">
        {word.type}
        {hlLabel && <span className="hl-badge ml-2">{hlLabel}</span>}
      </div>
    </div>
  );
}

function isPunctuation(char: string): boolean {
  return /^[，。、；：？！""''《》（）【】\s·—…]+$/.test(char);
}
