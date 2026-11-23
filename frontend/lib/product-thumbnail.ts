/** Neutral box for a SKU whose SKU master row names no photo. */
export const PLACEHOLDER_THUMBNAIL = "/images/products/placeholder.svg";

/**
 * Thumbnail of one SKU: the photo its SKU master row names (image_url), else the neutral box.
 * Never a photo picked by brand, which would show another product. Only a path on this site or an https
 * link is used, since an imported SKU master could hold any text.
 */
export function productThumbnail(imageUrl: string | null | undefined): string {
  const url = (imageUrl ?? "").trim();
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  if (/^https:\/\//i.test(url)) return url;
  return PLACEHOLDER_THUMBNAIL;
}
