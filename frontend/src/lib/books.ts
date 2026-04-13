/**
 * 书与目录的构建时加载
 * 所有 book.json / catalog.json 都很小（总共约 5MB），构建时 eager import 没问题
 */
import type { Book, BookIndex, Catalog, DocumentMeta, Group } from './types';

// index.json：所有书的概览
// 注意：eager import 的路径必须是字面量，不能用变量
import booksIndex from '../../../data/books/index.json';

// 每本书的 book.json 和 catalog.json
const bookJsonModules = import.meta.glob<{ default: Book }>(
  '../../../data/books/*/book.json',
  { eager: true }
);
const catalogModules = import.meta.glob<{ default: Catalog }>(
  '../../../data/books/*/catalog.json',
  { eager: true }
);

// 按 bookId 索引
const booksMap = new Map<string, Book>();
for (const [path, mod] of Object.entries(bookJsonModules)) {
  const book = mod.default;
  booksMap.set(book.id, book);
}

const catalogMap = new Map<string, Catalog>();
for (const [, mod] of Object.entries(catalogModules)) {
  const cat = mod.default;
  catalogMap.set(cat.bookId, cat);
}

// ============ 导出 ============

export function getAllBooks(): BookIndex[] {
  return (booksIndex.books as BookIndex[]).slice().sort((a, b) => a.order - b.order);
}

export function getBook(id: string): Book | undefined {
  return booksMap.get(id);
}

export function getCatalog(bookId: string): Catalog | undefined {
  return catalogMap.get(bookId);
}

// ============ 目录遍历工具 ============

/** 扁平化所有文档元数据（递归取所有 leaf） */
export function getAllDocuments(bookId: string): Array<DocumentMeta & { groupPath: string[] }> {
  const cat = catalogMap.get(bookId);
  if (!cat) return [];
  const out: Array<DocumentMeta & { groupPath: string[] }> = [];
  walk(cat.groups, [], out);
  return out;
}

function walk(
  groups: Group[],
  path: string[],
  out: Array<DocumentMeta & { groupPath: string[] }>,
) {
  for (const g of groups) {
    const nextPath = [...path, g.id];
    if (g.documents) {
      for (const d of g.documents) out.push({ ...d, groupPath: nextPath });
    }
    if (g.subgroups) walk(g.subgroups, nextPath, out);
  }
}

/** 按路径查找分组（支持多层） */
export function findGroup(bookId: string, path: string[]): Group | undefined {
  const cat = catalogMap.get(bookId);
  if (!cat) return undefined;
  let current: Group[] = cat.groups;
  let found: Group | undefined;
  for (const segment of path) {
    found = current.find((g) => g.id === segment);
    if (!found) return undefined;
    current = found.subgroups ?? [];
  }
  return found;
}

/** 找到某文档所在的分组路径（面包屑用） */
export function findDocumentPath(
  bookId: string,
  docId: string,
): { doc: DocumentMeta; path: Group[] } | undefined {
  const cat = catalogMap.get(bookId);
  if (!cat) return undefined;
  const result = searchDoc(cat.groups, docId, []);
  return result ?? undefined;
}

function searchDoc(
  groups: Group[],
  docId: string,
  pathAcc: Group[],
): { doc: DocumentMeta; path: Group[] } | null {
  for (const g of groups) {
    const nextPath = [...pathAcc, g];
    if (g.documents) {
      const found = g.documents.find((d) => d.id === docId);
      if (found) return { doc: found, path: nextPath };
    }
    if (g.subgroups) {
      const hit = searchDoc(g.subgroups, docId, nextPath);
      if (hit) return hit;
    }
  }
  return null;
}

// ============ 朝代装饰色（全站通用） ============

export const DYNASTY_COLOR: Record<string, string> = {
  pre_qin: '#8B6914',
  han: '#C84032',
  wei_jin: '#4A7C59',
  tang: '#2A5CAA',
  song: '#7B4B94',
  ming: '#B8860B',
  qing: '#1E4D6B',
};

export function dynastyColor(id: string): string {
  return DYNASTY_COLOR[id] ?? '#555';
}

// ============ 文档 URL 生成（构建时） ============

export function documentUrl(bookId: string, docId: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}/book/${bookId}/doc/${encodeURIComponent(docId)}`;
}

export function bookUrl(bookId: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}/book/${bookId}`;
}

export function groupUrl(bookId: string, path: string[]): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}/book/${bookId}/group/${path.map(encodeURIComponent).join('/')}`;
}
