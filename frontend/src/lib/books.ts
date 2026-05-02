/**
 * 书与目录的构建时加载
 * 所有 book.json / catalog.json 都很小（总共约 5MB），构建时 eager import 没问题
 */
import type {
  AuthorEntry,
  Book,
  BookIndex,
  Catalog,
  DocumentMeta,
  DynastyAuthorGroup,
  DynastyHighlightItem,
  DynastyStation,
  Group,
} from "./types";

// index.json：所有书的概览
// 注意：eager import 的路径必须是字面量，不能用变量
import booksIndex from "../../../data/books/index.json";

// curation/：首页文案与精选钩子（独立于主管线，可手工维护）
import dynastyOverviewRaw from "../../../data/curation/dynasty_overview.json";
import documentHooksRaw from "../../../data/curation/document_hooks.json";

interface DynastyOverviewEntry {
  tagline: string;
  subtitle: string;
  summary: string;
  highlights: string[];
}

const DYNASTY_OVERVIEW = (
  dynastyOverviewRaw as {
    dynasties: Record<string, DynastyOverviewEntry>;
  }
).dynasties;

const DOC_HOOKS = (documentHooksRaw as { hooks: Record<string, string> }).hooks;

// 每本书的 book.json 和 catalog.json
const bookJsonModules = import.meta.glob<{ default: Book }>(
  "../../../data/books/*/book.json",
  { eager: true },
);
const catalogModules = import.meta.glob<{ default: Catalog }>(
  "../../../data/books/*/catalog.json",
  { eager: true },
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
  return (booksIndex.books as BookIndex[])
    .slice()
    .sort((a, b) => a.order - b.order);
}

export function getBook(id: string): Book | undefined {
  return booksMap.get(id);
}

export function getCatalog(bookId: string): Catalog | undefined {
  return catalogMap.get(bookId);
}

// ============ 目录遍历工具 ============

/** 扁平化所有文档元数据（递归取所有 leaf） */
export function getAllDocuments(
  bookId: string,
): Array<DocumentMeta & { groupPath: string[] }> {
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
  pre_qin: "#8B6914",
  han: "#C84032",
  wei_jin: "#4A7C59",
  tang: "#2A5CAA",
  song: "#7B4B94",
  ming: "#B8860B",
  qing: "#1E4D6B",
};

export function dynastyColor(id: string): string {
  return DYNASTY_COLOR[id] ?? "#555";
}

// ============ 文档 URL 生成（构建时） ============

export function documentUrl(bookId: string, docId: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}/book/${bookId}/doc/${encodeURIComponent(docId)}`;
}

export function bookUrl(bookId: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}/book/${bookId}`;
}

export function groupUrl(bookId: string, path: string[]): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}/book/${bookId}/group/${path.map(encodeURIComponent).join("/")}`;
}

// ============ 首页朝代驿站 ============

/** 主入口书 id：当前只展示古文观止 */
export const PRIMARY_BOOK_ID = "guwenguanzhi";

/** 取一句话钩子，缺省回退到 title */
export function getDocumentHook(docId: string, fallback = ""): string {
  return DOC_HOOKS[docId] ?? fallback;
}

/**
 * 构建首页朝代驿站列表（按 catalog.groups 顺序，即历史时序）
 * 仅取主入口书 PRIMARY_BOOK_ID。未来若要跨书聚合，在此扩展。
 */
export function getDynastyStations(): DynastyStation[] {
  const cat = catalogMap.get(PRIMARY_BOOK_ID);
  if (!cat) return [];

  return cat.groups.map((g) => {
    const subgroups = g.subgroups ?? [];
    const totalDocs = subgroups.reduce(
      (s, sg) => s + (sg.documents?.length ?? 0),
      0,
    );
    const authors = subgroups.map((sg) => sg.name);

    const overview = DYNASTY_OVERVIEW[g.id];
    const period =
      (g.meta?.period as string | undefined) ?? g.description ?? "";

    // 拼装 highlights
    const highlights: DynastyHighlightItem[] = [];
    for (const docId of overview?.highlights ?? []) {
      const hit = findInGroup(subgroups, docId);
      if (!hit) continue;
      highlights.push({
        docId,
        title: hit.doc.title,
        author: hit.author,
        hook: DOC_HOOKS[docId] ?? hit.doc.title,
        bookId: PRIMARY_BOOK_ID,
        href: documentUrl(PRIMARY_BOOK_ID, docId),
      });
    }

    return {
      id: g.id,
      name: g.name,
      period,
      color: dynastyColor(g.id),
      tagline: overview?.tagline ?? "",
      subtitle: overview?.subtitle ?? "",
      summary: overview?.summary ?? g.description ?? "",
      totalDocs,
      totalAuthors: authors.length,
      authors,
      highlights,
      groupHref: groupUrl(PRIMARY_BOOK_ID, [g.id]),
    };
  });
}

/** 在朝代下的作者子组里找指定 docId */
function findInGroup(
  subgroups: Group[],
  docId: string,
): { doc: DocumentMeta; author: string } | null {
  for (const sg of subgroups) {
    const hit = sg.documents?.find((d) => d.id === docId);
    if (hit) return { doc: hit, author: sg.name };
  }
  return null;
}

// ============ 按作者浏览 ============

/**
 * 返回按朝代分组的全部作者（用于 /authors 页面）
 * 朝代顺序与 catalog.groups 一致
 */
export function getAuthorsByDynasty(): DynastyAuthorGroup[] {
  const cat = catalogMap.get(PRIMARY_BOOK_ID);
  if (!cat) return [];

  return cat.groups.map((g) => {
    const period =
      (g.meta?.period as string | undefined) ?? g.description ?? "";
    const authors: AuthorEntry[] = (g.subgroups ?? []).map((sg) => ({
      id: sg.id,
      name: sg.name,
      dynasty: g.id,
      dynastyName: g.name,
      bookId: PRIMARY_BOOK_ID,
      documentCount: sg.documents?.length ?? 0,
      documents: sg.documents ?? [],
    }));
    // 按篇目数倒序，凸显大家
    authors.sort((a, b) => b.documentCount - a.documentCount);

    return {
      dynasty: {
        id: g.id,
        name: g.name,
        period,
        color: dynastyColor(g.id),
      },
      authors,
    };
  });
}
