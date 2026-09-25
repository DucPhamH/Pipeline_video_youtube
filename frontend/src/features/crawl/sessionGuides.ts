/** Hướng dẫn phiên đăng nhập / copy cookie theo từng site — hiện trên SiteDetailPage. */

export type CrawlNeed = "ok" | "optional" | "required"

export type CookieCopyMethod = {
  title: string
  steps: string[]
  /** Ưu tiên khi extension/DevTools hay lỗi trên site này */
  recommended?: boolean
}

export type SessionGuide = {
  /** Một dòng — banner trên trang site */
  summary: string
  loginUrl: string
  /** Ghi chú domain (www vs không www, http/https…) */
  domainNote?: string
  /** Crawl được gì khi chưa có phiên */
  worksWithoutSession: string[]
  /** Crawl cần phiên khi nào */
  needsSession: Array<{ task: string; level: CrawlNeed; detail: string }>
  /** Tên cookie nên có trong chuỗi dán */
  keyCookies: Array<{ name: string; note: string }>
  copyMethods: CookieCopyMethod[]
  vipNote?: string
  extraNotes?: string[]
}

/** Các bước copy cookie dùng chung — ghép vào từng site nếu cần */
export const COMMON_COPY_METHODS: CookieCopyMethod[] = [
  {
    title: "Network tab (khuyên dùng — lấy cả HttpOnly)",
    recommended: true,
    steps: [
      "Mở đúng domain site, đăng nhập xong (CAPTCHA/Cloudflare nếu có).",
      "F12 → tab Network → F5 refresh trang.",
      "Click request đầu tiên (trang chủ hoặc index).",
      "Headers → Request Headers → dòng Cookie: → copy nguyên chuỗi.",
      "Dán vào ô bên dưới → Lưu → Thử phiên.",
    ],
  },
  {
    title: "DevTools → Application → Cookies",
    steps: [
      "F12 → Application (Chrome) / Storage (Firefox) → Cookies → chọn đúng domain.",
      "Gộp tay: name=value; name2=value2 (ít nhất các cookie quan trọng bên trên).",
      "Nếu có cf_clearance / cookie Cloudflare thì nên copy luôn.",
    ],
  },
  {
    title: "Cookie-Editor (extension)",
    steps: [
      "Cài Cookie-Editor trên Chrome/Firefox → Export → Header String.",
      "Một số site (vd wenku8) extension báo “no cookies” dù DevTools vẫn thấy — dùng Network tab thay thế.",
    ],
  },
]

export const SESSION_GUIDES: Record<string, SessionGuide> = {
  wenku8_net: {
    summary:
      "Quét thể loại cần cookie wenku8; book/chương free thường crawl được không cần phiên.",
    loginUrl: "https://www.wenku8.net/login.php",
    domainNote:
      "Luôn dùng www.wenku8.net. Cookie-Editor đôi khi báo trống dù DevTools vẫn thấy — copy từ Network tab.",
    worksWithoutSession: [
      "Thêm truyện bằng URL sách (vd /book/123.htm).",
      "Lấy mục lục + chương free qua URL book/chapter.",
    ],
    needsSession: [
      {
        task: "Quét thể loại (Quét nhiều)",
        level: "required",
        detail: "Trang articlelist.php redirect login.php nếu thiếu phiên.",
      },
      {
        task: "Chương VIP / khoá",
        level: "required",
        detail: "Cần account đã mua quyền + cookie đăng nhập.",
      },
    ],
    keyCookies: [
      { name: "PHPSESSID", note: "Phiên PHP" },
      { name: "jieqiUserInfo", note: "Bắt buộc — chứng minh đã login" },
      { name: "jieqiVisitInfo", note: "Thông tin visit/login" },
      { name: "cf_clearance", note: "Nên có — qua Cloudflare khi crawl" },
    ],
    copyMethods: [
      {
        title: "Network tab trên www.wenku8.net (khuyên dùng cho wenku8)",
        recommended: true,
        steps: [
          "Đăng nhập tại https://www.wenku8.net/login.php — thấy tên user góc trái.",
          "F12 → Network → F5 tại index.php.",
          "Copy toàn bộ dòng Cookie: trong Request Headers.",
          "Kiểm tra chuỗi có jieqiUserInfo= và PHPSESSID=.",
        ],
      },
      ...COMMON_COPY_METHODS.filter((m) => !m.recommended),
    ],
    extraNotes: [
      "Probe “Thử phiên” chỉ kiểm tra trang chủ — nếu probe OK mà quét thể loại vẫn lỗi, copy lại cookie sau khi mở đúng trang list.",
      "Cookie hết hạn sau vài ngày/tuần — đăng nhập lại trên browser rồi copy mới.",
    ],
  },

  qidian_com: {
    summary:
      "Anti-bot nặng — hầu như cần cookie Qidian (ywguid + phiên login) cho list và chương. VIP cần account đã mua + Node decrypt server.",
    loginUrl: "https://passport.qidian.com/",
    domainNote: "Cookie lấy từ www.qidian.com sau khi đăng nhập passport Qidian.",
    worksWithoutSession: ["Hiếm khi — anti-bot thường chặn ngay cả trang list."],
    needsSession: [
      {
        task: "Quét thể loại",
        level: "required",
        detail: "Trang list trả HTML anti-bot ngắn nếu thiếu cookie.",
      },
      {
        task: "Đọc chương free",
        level: "required",
        detail: "Playwright + cookie mới ổn định; thiếu cookie hay gặp trang chặn.",
      },
      {
        task: "Chương VIP",
        level: "required",
        detail: "Cookie ywguid + quyền VIP trên account; server giải mã Node.",
      },
    ],
    keyCookies: [
      { name: "ywguid", note: "Quan trọng cho anti-bot và VIP decrypt" },
      { name: "ywkey", note: "Thường đi kèm ywguid" },
      { name: "ywguidhash / các cookie passport", note: "Phiên đăng nhập Qidian" },
    ],
    copyMethods: [...COMMON_COPY_METHODS],
    vipNote:
      "Không crack thanh toán — chỉ đọc chương VIP nếu account đã mua. Server cần Node 18+ cho giải mã.",
    extraNotes: [
      "Đăng nhập xong mở https://www.qidian.com → F5 → copy Cookie từ Network.",
      "Nếu probe fail: thử đăng nhập lại, xong challenge trên browser, copy cookie mới.",
    ],
  },

  ciweimao_com: {
    summary:
      "Xem list thể loại thường không cần login; đọc chương hay bị CAPTCHA/API lỗi nếu thiếu cookie. VIP ảnh cần account + OCR.",
    loginUrl: "https://www.ciweimao.com/login",
    worksWithoutSession: [
      "Quét danh sách thể loại (list book).",
      "Lấy mục lục chương qua URL sách.",
    ],
    needsSession: [
      {
        task: "Đọc nội dung chương",
        level: "required",
        detail: "API chapter trả 验证码 / lỗi 400001 nếu chưa có phiên.",
      },
      {
        task: "Chương VIP (ảnh)",
        level: "required",
        detail: "Account đã mua + cookie; server OCR ảnh VIP.",
      },
    ],
    keyCookies: [
      { name: "ciweimao cookie session", note: "Copy nguyên chuỗi Cookie sau login" },
      { name: "token / uid (nếu có)", note: "Thường nằm trong cùng header Cookie" },
    ],
    copyMethods: [...COMMON_COPY_METHODS],
    extraNotes: [
      "Sau login, mở một chương free bất kỳ → F12 Network → copy Cookie từ request chapter.",
      "CAPTCHA trên site phải giải tay trên browser — app không tự giải.",
    ],
  },

  faloo_com: {
    summary: "Chương free HTML OK không cần phiên; VIP/ảnh cần cookie Faloo.",
    loginUrl: "https://b.faloo.com/",
    domainNote: "Site crawl dùng b.faloo.com — login trên domain Faloo tương ứng.",
    worksWithoutSession: [
      "Quét thể loại / bảng xếp hạng.",
      "Chương miễn phí (HTML div.noveContent).",
      "Thêm truyện bằng URL.",
    ],
    needsSession: [
      {
        task: "Chương VIP / ảnh",
        level: "required",
        detail: "Nội dung khoá — cần cookie account đã mua VIP.",
      },
    ],
    keyCookies: [{ name: "(toàn bộ Cookie sau login)", note: "Copy header Cookie từ b.faloo.com" }],
    copyMethods: [...COMMON_COPY_METHODS],
  },

  n17k_com: {
    summary:
      "Cookie challenge acw_sc tự xử lý; chương VIP/khoá cần cookie đăng nhập 17K.",
    loginUrl: "https://passport.17k.com/",
    worksWithoutSession: [
      "Quét thể loại.",
      "Chương free sau khi server vượt challenge JS.",
      "Thêm truyện bằng URL.",
    ],
    needsSession: [
      {
        task: "Chương VIP / khoá",
        level: "required",
        detail: "Trang chương báo VIP — cần cookie account có quyền.",
      },
    ],
    keyCookies: [
      { name: "17k cookie login", note: "Sau login passport.17k.com" },
      { name: "GUID", note: "Challenge tự sinh — không cần copy tay" },
    ],
    copyMethods: [...COMMON_COPY_METHODS],
    extraNotes: [
      "Không cần copy GUID/acw_sc tay — backend tự giải challenge.",
      "Chỉ dán phiên khi cần đọc chương VIP.",
    ],
  },

  zhihu_com: {
    summary:
      "盐选专栏 bắt buộc cookie Zhihu (z_c0 + d_c0). Không có hội viên/đã mua thì không đọc được nội dung.",
    loginUrl: "https://www.zhihu.com/signin",
    domainNote: "Cookie lấy từ www.zhihu.com (không dùng story.zhihu.com APP-only).",
    worksWithoutSession: [],
    needsSession: [
      {
        task: "Thêm cột / đọc chương 盐选",
        level: "required",
        detail: "Thiếu z_c0/d_c0 → 401 hoặc trang login; thiếu quyền mua → nội dung trống.",
      },
      {
        task: "Quét thể loại",
        level: "required",
        detail: "Zhihu không có genre kiểu biquge — khuyến nghị Thêm URL cột paid_column.",
      },
    ],
    keyCookies: [
      { name: "z_c0", note: "Phiên đăng nhập — bắt buộc" },
      { name: "d_c0", note: "Ký header x-zse-96 — bắt buộc" },
    ],
    copyMethods: [...COMMON_COPY_METHODS],
    vipNote:
      "Chỉ crawl cột/chương account đã có quyền đọc (盐选会员 hoặc đã mua). Không bypass thanh toán.",
    extraNotes: [
      "URL đúng: https://www.zhihu.com/market/paid_column/<id>",
      "Link APP story.zhihu.com/manuscript/... đổi thành market/paid_column/... trên web.",
      "Cookie hết hạn nhanh — nếu lỗi login, đăng nhập lại và copy Cookie mới từ Network.",
    ],
  },
}

export function getSessionGuide(sourceKey: string): SessionGuide | undefined {
  return SESSION_GUIDES[sourceKey]
}

const NEED_LABELS: Record<CrawlNeed, string> = {
  ok: "Không cần",
  optional: "Tuỳ trường hợp",
  required: "Cần phiên",
}

export function crawlNeedLabel(level: CrawlNeed): string {
  return NEED_LABELS[level]
}
