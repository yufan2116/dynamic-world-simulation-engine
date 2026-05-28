/** 将后端返回的 /static/... 路径转为可加载 URL（走 Vite 代理）。 */
export function resolveImageSrc(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (!isUsableImageUrl(url)) return undefined;
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) {
    return url;
  }
  return url.startsWith("/") ? url : `/${url}`;
}

/** 占位图 URL 不算「已生成」资源，避免显示破损红块。 */
export function isUsableImageUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  return !url.includes("placeholder");
}
