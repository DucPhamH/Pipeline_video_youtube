/** Bảng màu bìa chọn lọc: nền đậm + vòng tròn trang trí sáng. */
const PALETTE = [
  { bg: "#0B5E4A", orb: "#2BD4A0" }, // deep jade
  { bg: "#2A3F8F", orb: "#7FA2FF" }, // cobalt
  { bg: "#7A2E3B", orb: "#FF8DA1" }, // wine
  { bg: "#7A4B06", orb: "#F5A524" }, // amber-brown
  { bg: "#0F5866", orb: "#5FD3E6" }, // teal
  { bg: "#4E2A6B", orb: "#C59BFF" }, // plum
] as const

function hash(text: string): number {
  let h = 0
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)!) >>> 0
  return h
}

/** Màu bìa ổn định theo tên — dùng chung cho chỗ cần tông của cuốn sách (vd. hero). */
export function coverColors(title: string): { bg: string; orb: string } {
  return PALETTE[hash(title || "?") % PALETTE.length]
}
