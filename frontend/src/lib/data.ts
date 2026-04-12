/**
 * 数据加载工具
 * 从 data/ 目录读取 catalog.json 和文章 JSON
 */

// catalog.json 在构建时导入
import catalogData from '../../../data/catalog.json';

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
  id: string;
  name: string;
  dynasty: string;
  bio: string;
}

export interface ArticleMeta {
  id: string;
  title: string;
  author: string;
  source: string;
  volume: number;
  dynasty: string;
  raw_file: string;
  paragraphs_count: number;
}

export interface ArticleFull {
  id: string;
  title: string;
  author: Author;
  source: string;
  dynasty: string;
  volume: number;
  background: string;
  appreciation: string;
  tags: string[];
  paragraphs: Paragraph[];
}

export interface AuthorEntry {
  id: string;
  name: string;
  dynasty: string;
  bio: string;
  articles: ArticleMeta[];
}

export interface Dynasty {
  id: string;
  name: string;
  period: string;
  authors: AuthorEntry[];
  article_count: number;
}

export interface Catalog {
  dynasties: Dynasty[];
}

export function getCatalog(): Catalog {
  return catalogData as Catalog;
}

export function getDynasties(): Dynasty[] {
  return getCatalog().dynasties;
}

export function getDynasty(id: string): Dynasty | undefined {
  return getDynasties().find(d => d.id === id);
}

export function getAuthor(authorId: string): AuthorEntry | undefined {
  for (const dynasty of getDynasties()) {
    const author = dynasty.authors.find(a => a.id === authorId);
    if (author) return author;
  }
  return undefined;
}

export function getAllArticles(): ArticleMeta[] {
  const articles: ArticleMeta[] = [];
  for (const dynasty of getDynasties()) {
    for (const author of dynasty.authors) {
      articles.push(...author.articles);
    }
  }
  return articles;
}

export function getDynastyName(id: string): string {
  const names: Record<string, string> = {
    pre_qin: '先秦',
    han: '两汉',
    wei_jin: '魏晋南北朝',
    tang: '唐',
    song: '宋',
    ming: '明',
  };
  return names[id] || id;
}

/**
 * 加载单篇文章的完整 JSON（含翻译和词注释）
 * 用于文章阅读页的 getStaticPaths
 */
export async function loadArticle(dynastyId: string, articleId: string): Promise<ArticleFull | null> {
  try {
    // 使用 Vite 的 import.meta.glob 动态导入
    const modules = import.meta.glob('../../../data/articles/**/*.json', { eager: true });
    const key = `../../../data/articles/${dynastyId}/${articleId}.json`;
    const mod = modules[key] as { default: ArticleFull } | undefined;
    return mod?.default ?? null;
  } catch {
    return null;
  }
}
