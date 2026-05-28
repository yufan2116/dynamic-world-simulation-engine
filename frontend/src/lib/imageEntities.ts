import { isUsableImageUrl } from "./imageUrl";

/** 从 API 的 image_entities / npc_portraits 合并肖像 URL 表 */
export function mergePortraitMaps(  ...sources: Array<Record<string, string> | Record<string, { url?: string }> | undefined>
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const src of sources) {
    if (!src) continue;
    for (const [key, val] of Object.entries(src)) {
      if (typeof val === "string" && isUsableImageUrl(val)) {
        const name = key.startsWith("npc:") ? key.slice(4) : key;
        out[name] = val;
        continue;
      }
      if (val && typeof val === "object" && "url" in val && isUsableImageUrl(val.url)) {
        const name = key.startsWith("npc:") ? key.slice(4) : key;
        out[name] = String(val.url);
      }
    }
  }
  return out;
}
