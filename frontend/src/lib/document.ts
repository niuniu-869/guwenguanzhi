/**
 * 文档内容客户端加载
 * documents/*.json 由 scripts/sync_frontend_data.py 同步到 public/data/
 * 运行时 fetch，避免编译时把 GB 级内容打进 bundle
 */
import type { Document } from './types';

export interface DocumentLoadResult {
  doc: Document | null;
  error: string | null;
}

/**
 * 路径规则：
 *   古文观止：/data/books/guwenguanzhi/documents/<dynasty>/<docId>.json
 *   史记：    /data/books/shiji/documents/<docId>.json
 *
 * bookId='guwenguanzhi' 的 docId 形如 "001_郑伯克段于鄢"，朝代信息从 catalog 查
 * bookId='shiji' 的 docId 形如 "001"，无子目录
 */
export function documentJsonPath(
  bookId: string,
  docId: string,
  subdir?: string,
): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const parts = ['data', 'books', bookId, 'documents'];
  if (subdir) parts.push(subdir);
  parts.push(`${docId}.json`);
  return `${base}/${parts.join('/')}`;
}

export async function loadDocument(
  bookId: string,
  docId: string,
  subdir?: string,
): Promise<DocumentLoadResult> {
  const url = documentJsonPath(bookId, docId, subdir);
  try {
    const res = await fetch(url);
    if (!res.ok) return { doc: null, error: `HTTP ${res.status}` };
    const doc = (await res.json()) as Document;
    return { doc, error: null };
  } catch (err) {
    return { doc: null, error: err instanceof Error ? err.message : String(err) };
  }
}
