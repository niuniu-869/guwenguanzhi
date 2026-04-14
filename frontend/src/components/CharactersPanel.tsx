/**
 * 人物卡面板（v3 新增）
 *
 * 行为：
 * - `characters` 为空或未提供 → 不渲染（自动对纯山水/抒情篇消失）
 * - 有人物时，展示可折叠面板：身份 / 立场 / 动机 / 关系
 *
 * 设计原则：
 * - 聚合视图，不堆文字；关系用徽章形式
 * - 与段注解并置，不抢眼，默认折叠展开交由用户
 */
import { useState } from "react";
import type { Character } from "../lib/types";

interface Props {
  characters?: Character[];
}

export default function CharactersPanel({ characters }: Props) {
  const [open, setOpen] = useState<boolean>(true);

  if (!characters || characters.length === 0) return null;

  return (
    <section className="characters-panel">
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-ink-light tracking-wider">
          人物关系（{characters.length}）
        </h2>
        <button
          type="button"
          className="text-xs text-ink-faint hover:text-ink-light transition-colors"
          onClick={() => setOpen((p) => !p)}
        >
          {open ? "收起" : "展开"}
        </button>
      </header>

      {open && (
        <div>
          {characters.map((c) => (
            <CharacterCard key={c.id} character={c} />
          ))}
        </div>
      )}
    </section>
  );
}

function CharacterCard({ character }: { character: Character }) {
  const aliases =
    character.aliases && character.aliases.length > 0
      ? character.aliases.join(" · ")
      : null;

  return (
    <article className="character-card">
      <div>
        <span className="cc-name">{character.name}</span>
        {aliases && <span className="cc-alias">{aliases}</span>}
      </div>
      {character.role && (
        <div className="cc-field">
          <span className="cc-label">身份</span>
          {character.role}
        </div>
      )}
      {character.stance && (
        <div className="cc-field">
          <span className="cc-label">立场</span>
          {character.stance}
        </div>
      )}
      {character.motive && (
        <div className="cc-field">
          <span className="cc-label">动机</span>
          {character.motive}
        </div>
      )}
      {character.relations && character.relations.length > 0 && (
        <div className="cc-field">
          <span className="cc-label">关系</span>
          {character.relations.map((r, i) => (
            <span key={i} className="cc-rel" title={r.note ?? undefined}>
              <span className="text-ink-faint">{r.type}</span>
              <span>· {r.target}</span>
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
