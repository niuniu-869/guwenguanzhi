/**
 * 文档阅读器（React 岛屿）
 * client 端 fetch 文档 JSON，渲染完整阅读体验
 * 避免编译时把 GB 级内容打进 bundle
 */
import { useEffect, useState } from "react";
import type { Document } from "../lib/types";
import { loadDocument } from "../lib/document";
import ReadingView from "./ReadingView";
import CharactersPanel from "./CharactersPanel";

interface Props {
  bookId: string;
  docId: string;
  subdir?: string;
}

export default function DocumentReader({ bookId, docId, subdir }: Props) {
  const [state, setState] = useState<{
    doc: Document | null;
    error: string | null;
    loading: boolean;
  }>({ doc: null, error: null, loading: true });

  useEffect(() => {
    let cancelled = false;
    setState({ doc: null, error: null, loading: true });
    loadDocument(bookId, docId, subdir).then((res) => {
      if (cancelled) return;
      setState({ doc: res.doc, error: res.error, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [bookId, docId, subdir]);

  if (state.loading) {
    return (
      <div className="py-16 text-center text-ink-faint">
        <div className="inline-block animate-pulse text-sm tracking-widest">
          文本 · 载入中
        </div>
      </div>
    );
  }

  if (state.error || !state.doc) {
    return (
      <div className="py-12 text-center">
        <p className="text-ink-light mb-2">文档加载失败</p>
        <p className="text-xs text-ink-faint">{state.error ?? "未知错误"}</p>
      </div>
    );
  }

  const doc = state.doc;
  const intro = doc.summary || doc.background;

  return (
    <div>
      {/* 简介 / 背景 */}
      {intro && (
        <section className="mb-10 px-5 py-4 bg-silk rounded border border-border-light">
          <h2 className="text-sm font-semibold text-ink-light mb-2 tracking-wider">
            {doc.summary ? "内容概要" : "写作背景"}
          </h2>
          <p className="text-sm text-ink-light leading-relaxed">{intro}</p>
        </section>
      )}

      {/* v3 新增：人物关系卡（无人物则组件自行隐藏） */}
      <CharactersPanel characters={doc.characters} />

      {/* 正文阅读区 */}
      <section className="mb-12">
        <ReadingView paragraphs={doc.paragraphs} />
      </section>

      <hr className="divider-ink" />

      {/* 赏析 */}
      {doc.appreciation && (
        <section className="mb-10">
          <h2 className="font-serif text-xl font-semibold text-ink mb-4">
            赏析
          </h2>
          <p className="text-ink-light leading-relaxed whitespace-pre-line">
            {doc.appreciation}
          </p>
        </section>
      )}

      {/* 关键人物（史记特有） */}
      {doc.keyFigures && doc.keyFigures.length > 0 && (
        <section className="mb-10 px-5 py-4 bg-card rounded border border-border-light">
          <h2 className="text-sm font-semibold text-ink-light mb-2 tracking-wider">
            关键人物
          </h2>
          <div className="flex flex-wrap gap-2">
            {doc.keyFigures.map((p) => (
              <span
                key={p}
                className="text-sm text-ink-light px-2 py-0.5 bg-silk rounded"
              >
                {p}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* 历史时期 */}
      {doc.historicalPeriod && (
        <section className="mb-10 text-sm text-ink-faint text-center">
          <span>历史时期：{doc.historicalPeriod}</span>
        </section>
      )}

      {/* 作者简介 */}
      {doc.author?.bio && (
        <section className="mb-10 px-5 py-4 bg-card rounded border border-border-light">
          <h2 className="text-sm font-semibold text-ink-light mb-2 tracking-wider">
            关于 {doc.author.name}
          </h2>
          <p className="text-sm text-ink-light leading-relaxed">
            {doc.author.bio}
          </p>
        </section>
      )}
    </div>
  );
}
