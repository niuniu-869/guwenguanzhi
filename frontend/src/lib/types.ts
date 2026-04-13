/**
 * 多书架构统一类型定义
 * 一套 schema 适配古文观止、二十四史等不同结构的古籍
 */

// ============ 书 ============

export type StructureType = 'collection' | 'jizhuan' | 'biannian';

export interface BookIndex {
  /** 稳定 ID，用于路由与目录 */
  id: string;
  /** 中文名 */
  name: string;
  /** 展示名（繁体/书法体） */
  displayName: string;
  /** 单作者（纪传体史书等） */
  author: string | null;
  /** 编者（合集类） */
  editor: string | null;
  /** 所属朝代 id */
  dynasty: string;
  /** 朝代 · 成书/创作时间 */
  period: string;
  /** 简介 */
  summary: string;
  /** 文档总数 */
  totalDocuments: number;
  structureType: StructureType;
  cover: { theme: string; pattern: string } | null;
  /** 书架排序 */
  order: number;
}

export interface Book extends BookIndex {
  totalChars?: number;
  totalParagraphs?: number;
  totalAuthors?: number;
  hierarchy: string[];
  source: string;
  license: string;
}

// ============ 目录 ============

/**
 * Group 可嵌套 Group，叶子节点是 DocumentMeta。
 * 这样一套 schema 同时支持：
 *  - 古文观止：dynasty → author → document（3 层）
 *  - 史记：category → document（2 层）
 *  - 未来资治通鉴：chronology → year → document（3 层）
 */
export interface Group {
  id: string;
  name: string;
  description?: string;
  meta?: Record<string, unknown>;
  subgroups?: Group[];
  documents?: DocumentMeta[];
}

export interface DocumentMeta {
  id: string;
  title: string;
  paragraphCount: number;
  juan?: number;
  author?: string;
  source?: string;
  volume?: number;
  charCount?: number;
  tags?: string[];
  legacyId?: string;
}

export interface Catalog {
  bookId: string;
  hierarchy: string[];
  groups: Group[];
}

// ============ 文档内容 ============

export interface Word {
  word: string;
  pinyin: string;
  meaning: string;
  type: string;
}

export interface Sentence {
  original: string;
  translation: string;
  words: Word[];
}

export interface Paragraph {
  original: string;
  translation: string;
  sentences: Sentence[];
}

export interface Author {
  name: string;
  dynasty: string;
  bio?: string;
}

export interface Document {
  id: string;
  bookId: string;
  title: string;
  author: Author;
  /** 内容概要（史记风格） */
  summary?: string;
  /** 创作背景（古文观止风格） */
  background?: string;
  /** 赏析 */
  appreciation: string;
  tags: string[];
  /** 可选字段 */
  source?: string;
  keyFigures?: string[];
  historicalPeriod?: string;
  juan?: number;
  category?: string;
  categoryName?: string;
  paragraphs: Paragraph[];
}
