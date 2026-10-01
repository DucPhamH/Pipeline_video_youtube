"""File CẤU HÌNH/WIRING nguồn — DUY NHẤT nơi liệt kê site + thể loại.

Quy ước select thể loại (chốt theo phản hồi thật):
  - Mỗi site có BAO NHIÊU thể loại trên menu/nav THẬT thì select có BẤY NHIÊU.
  - KHÔNG tự chế option (không nhân bản "Hot theo thể loại", không bịa genre
    cho 2 site "trông đều nhau").
  - Ranking/search chỉ seed khi đó là link THẬT trên site VÀ cần cho nghiệp
    vụ — hiện chỉ giữ search Kinh dị trên bqgxs (site không có mục 恐怖).
  - `genre_key` trùng khái niệm giữa các site → cùng key + nhãn Việt giống nhau.
"""
from crawl.domain.ports import SourcePort
from crawl.infrastructure.sources.bgq99_cc_source import Bgq99CcSource
from crawl.infrastructure.sources.biquge365_net_source import Biquge365NetSource
from crawl.infrastructure.sources.biqvgeu_cc_source import BiqvgeuCcSource
from crawl.infrastructure.sources.bqg2_com_source import Bqg2ComSource
from crawl.infrastructure.sources.bqge_cc_source import BqgeCcSource
from crawl.infrastructure.sources.bqgxs_com_source import BqgxsComSource
from crawl.infrastructure.sources.bxg123_cc_source import Bxg123CcSource
from crawl.infrastructure.sources.demo_local_source import DemoLocalSource
from crawl.infrastructure.sources.diandingnnn_cc_source import DiandingnnnCcSource
from crawl.infrastructure.sources.eights_tw_com_source import EightsTwComSource
from crawl.infrastructure.sources.faloo_com_source import FalooComSource
from crawl.infrastructure.sources.fsshu_com_source import FsshuComSource
from crawl.infrastructure.sources.linovelib_com_source import LinovelibComSource
from crawl.infrastructure.sources.n17k_com_source import N17kComSource
from crawl.infrastructure.sources.piaotia_com_source import PiaotiaComSource
from crawl.infrastructure.sources.powanjuan_cc_source import PowanjuanCcSource
from crawl.infrastructure.sources.qbtr_cc_source import QbtrCcSource
from crawl.infrastructure.sources.ixdzs_tw_source import IxdzsTwSource
from crawl.infrastructure.sources.daysneo_com_source import DaysneoComSource
from crawl.infrastructure.sources.kakuyomu_com_source import KakuyomuComSource
from crawl.infrastructure.sources.novelba_com_source import NovelbaComSource
from crawl.infrastructure.sources.novelpia_com_source import NovelpiaComSource
from crawl.infrastructure.sources.quanben_io_source import QuanbenIoSource
from crawl.infrastructure.sources.qidian_com_source import QidianComSource
from crawl.infrastructure.sources.syosetu_com_source import SyosetuComSource
from crawl.infrastructure.sources.truyenfull_vn_source import TruyenfullVnSource
from crawl.infrastructure.sources.truyenfull_today_source import TruyenfullTodaySource
from crawl.infrastructure.sources.dtruyen_com_source import DtruyenComSource
from crawl.infrastructure.sources.sstruyen_net_source import SstruyenNetSource
from crawl.infrastructure.sources.docln_net_source import DoclnNetSource
from crawl.infrastructure.sources.esjzone_cc_source import EsjzoneCcSource
from crawl.infrastructure.sources.zhihu_com_source import ZhihuComSource
from crawl.infrastructure.sources.ttkan_co_source import TtkanCoSource
from crawl.infrastructure.sources.trxs_cc_source import TrxsCcSource
from crawl.infrastructure.sources.wenku8_net_source import Wenku8NetSource
from crawl.infrastructure.sources.ciweimao_com_source import CiweimaoComSource
from crawl.infrastructure.sources.zw85_com_source import Zw85ComSource
from crawl.infrastructure.sources.zongheng_com_source import ZonghengComSource
from crawl.infrastructure.sources.jjwxc_net_source import JjwxcNetSource
from crawl.infrastructure.sources.shubaow_net_source import ShubaowNetSource
from crawl.infrastructure.sources.tadu_com_source import TaduComSource
from crawl.infrastructure.sources.alphapolis_co_jp_source import AlphapolisCoJpSource
from crawl.infrastructure.sources.munpia_com_source import MunpiaComSource
from crawl.infrastructure.sources.blqiuge_cc_source import BlqiugeCcSource
from crawl.infrastructure.sources.pixiv_net_source import PixivNetSource
from platform_.config import config

_bqgxs_com = BqgxsComSource()
_bgq99_cc = Bgq99CcSource()
_fsshu_com = FsshuComSource()
_biquge365_net = Biquge365NetSource()
_powanjuan_cc = PowanjuanCcSource()
_zw85_com = Zw85ComSource()
_biqvgeu_cc = BiqvgeuCcSource()
_diandingnnn_cc = DiandingnnnCcSource()
_eights_tw_com = EightsTwComSource()
_bqg2_com = Bqg2ComSource()
_bqge_cc = BqgeCcSource()
_bxg123_cc = Bxg123CcSource()
_trxs_cc = TrxsCcSource()
_qbtr_cc = QbtrCcSource()
_faloo_com = FalooComSource()
_piaotia_com = PiaotiaComSource()
_linovelib_com = LinovelibComSource()
_n17k_com = N17kComSource()
_wenku8_net = Wenku8NetSource()
_ciweimao_com = CiweimaoComSource()
_qidian_com = QidianComSource()
_syosetu_com = SyosetuComSource()
_kakuyomu_com = KakuyomuComSource()
_novelba_com = NovelbaComSource()
_daysneo_com = DaysneoComSource()
_novelpia_com = NovelpiaComSource()
_truyenfull_vn = TruyenfullVnSource()
_truyenfull_today = TruyenfullTodaySource()
_dtruyen_com = DtruyenComSource()
_sstruyen_net = SstruyenNetSource()
_docln_net = DoclnNetSource()
_esjzone_cc = EsjzoneCcSource()
_zhihu_com = ZhihuComSource()
_ixdzs_tw = IxdzsTwSource()
_ttkan_co = TtkanCoSource()
_quanben_io = QuanbenIoSource()
_zongheng_com = ZonghengComSource()
_jjwxc_net = JjwxcNetSource()
_shubaow_net = ShubaowNetSource()
_tadu_com = TaduComSource()
_alphapolis_co_jp = AlphapolisCoJpSource()
_munpia_com = MunpiaComSource()
_blqiuge_cc = BlqiugeCcSource()
_pixiv_net = PixivNetSource()
_demo_local = DemoLocalSource(fixtures_dir=config.fixtures_dir)

SOURCES: dict[str, SourcePort] = {
    _bqgxs_com.key: _bqgxs_com,
    _bgq99_cc.key: _bgq99_cc,
    _fsshu_com.key: _fsshu_com,
    _biquge365_net.key: _biquge365_net,
    _powanjuan_cc.key: _powanjuan_cc,
    _zw85_com.key: _zw85_com,
    _biqvgeu_cc.key: _biqvgeu_cc,
    _diandingnnn_cc.key: _diandingnnn_cc,
    _eights_tw_com.key: _eights_tw_com,
    _bqg2_com.key: _bqg2_com,
    _bqge_cc.key: _bqge_cc,
    _bxg123_cc.key: _bxg123_cc,
    _trxs_cc.key: _trxs_cc,
    _qbtr_cc.key: _qbtr_cc,
    _faloo_com.key: _faloo_com,
    _piaotia_com.key: _piaotia_com,
    _linovelib_com.key: _linovelib_com,
    _n17k_com.key: _n17k_com,
    _wenku8_net.key: _wenku8_net,
    _ciweimao_com.key: _ciweimao_com,
    _qidian_com.key: _qidian_com,
    _syosetu_com.key: _syosetu_com,
    _kakuyomu_com.key: _kakuyomu_com,
    _novelba_com.key: _novelba_com,
    _daysneo_com.key: _daysneo_com,
    _novelpia_com.key: _novelpia_com,
    _truyenfull_vn.key: _truyenfull_vn,
    _truyenfull_today.key: _truyenfull_today,
    _dtruyen_com.key: _dtruyen_com,
    _sstruyen_net.key: _sstruyen_net,
    _docln_net.key: _docln_net,
    _esjzone_cc.key: _esjzone_cc,
    _zhihu_com.key: _zhihu_com,
    _ixdzs_tw.key: _ixdzs_tw,
    _ttkan_co.key: _ttkan_co,
    _quanben_io.key: _quanben_io,
    _zongheng_com.key: _zongheng_com,
    _jjwxc_net.key: _jjwxc_net,
    _shubaow_net.key: _shubaow_net,
    _tadu_com.key: _tadu_com,
    _alphapolis_co_jp.key: _alphapolis_co_jp,
    _munpia_com.key: _munpia_com,
    _blqiuge_cc.key: _blqiuge_cc,
    _pixiv_net.key: _pixiv_net,
}
# Nguồn demo đọc file trên đĩa — chỉ đăng ký khi bật CRAWL_ENABLE_DEMO_SOURCE
# (test/dev). Tắt thì dry-run / thêm truyện với source_key=demo_local 404.
if config.crawl_enable_demo_source:
    SOURCES[_demo_local.key] = _demo_local

# biquge.pro đã gỡ (HTTP 520 dai dẳng trên /novel/*) — genre cũ trong DB
# bị tắt tự động qua catalog_genre_keys() lúc startup.
GENRE_SEEDS = [
    # bqgxs.com không có mục Kinh dị trên nav — search từ khoá thật trên site.
    {
        "source_key": "bqgxs_com",
        "genre_key": "horror_search",
        "label": "Tìm kiếm: Kinh dị (恐怖)",
        "enabled": True,
        "list_url": "https://www.bqgxs.com/search.php?q=%E6%81%90%E6%80%96",
    },
]
if config.crawl_enable_demo_source:
    GENRE_SEEDS.append(
        {
            "source_key": "demo_local",
            "genre_key": "demo",
            "label": "[Demo] Nguồn test cục bộ",
            "list_url": "demo",
            "enabled": True,
        }
    )

# bqgxs.com nav thật: 玄幻/武侠/都市/历史/网游/科幻/言情/其他 — /list{1..8}/
_BQGXS_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", 1),
    ("wuxia", "Võ hiệp/Tu chân (武侠)", 2),
    ("urban", "Đô thị (都市)", 3),
    ("historical", "Lịch sử (历史)", 4),
    ("game", "Du hí/Game (网游)", 5),
    ("scifi", "Khoa huyễn (科幻)", 6),
    ("romance", "Ngôn tình (言情)", 7),
    ("other", "Khác (其他)", 8),
]
for _key, _label, _id in _BQGXS_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "bqgxs_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.bqgxs.com/list{_id}/",
            "enabled": False,
        }
    )

# bgq99.cc nav: 玄幻/武侠/都市/历史/网游/科幻/女生
_BGQ99_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (武侠)", "wuxia", False),
    ("urban", "Đô thị (都市)", "dushi", False),
    ("historical", "Lịch sử (历史)", "lishi", False),
    ("game", "Du hí/Game (网游)", "wangyou", False),
    ("scifi", "Khoa huyễn (科幻)", "kehuan", False),
    ("female", "Ngôn tình nữ (女生)", "mm", False),
]
for _key, _label, _slug, _enabled in _BGQ99_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "bgq99_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.bgq99.cc/{_slug}/",
            "enabled": _enabled,
        }
    )

# fsshu.com nav: cùng kiểu list1..8 như bqgxs
_FSSHU_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", 1, True),
    ("wuxia", "Võ hiệp/Tu chân (武侠)", 2, False),
    ("urban", "Đô thị (都市)", 3, False),
    ("historical", "Lịch sử (历史)", 4, False),
    ("game", "Du hí/Game (网游)", 5, False),
    ("scifi", "Khoa huyễn (科幻)", 6, False),
    ("romance", "Ngôn tình (言情)", 7, False),
    ("other", "Khác (其他)", 8, False),
]
for _key, _label, _id, _enabled in _FSSHU_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "fsshu_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"http://www.fsshu.com/list{_id}/",
            "enabled": _enabled,
        }
    )

# biquge365.net nav: /sort/{n}_1/
_BIQUGE365_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻魔法)", 1, False),
    ("wuxia", "Võ hiệp/Tu chân (仙侠修真)", 2, False),
    ("urban", "Đô thị (都市言情)", 3, False),
    ("game", "Du hí/Game (网游动漫)", 4, False),
    ("scifi", "Khoa huyễn (科幻小说)", 5, False),
    ("horror", "Kinh dị (恐怖灵异)", 6, True),
    ("historical", "Lịch sử (历史军事)", 7, False),
    ("other", "Khác (其他小说)", 8, False),
]
for _key, _label, _id, _enabled in _BIQUGE365_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "biquge365_net",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.biquge365.net/sort/{_id}_1/",
            "enabled": _enabled,
        }
    )

# powanjuan.cc nav thư mục thể loại (encoding GBK trên site)
_POWANJUAN_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", "wxxz", False),
    ("wuxia", "Võ hiệp/Tu chân (武侠修真)", "wxxz2", False),
    ("urban", "Đô thị (都市情感)", "dsyq", False),
    ("scifi", "Khoa huyễn (科幻魔法)", "khjj", False),
    ("game", "Du hí/Game (游戏竞技)", "yxjj", False),
    ("horror", "Kinh dị (鬼话悬疑)", "ghxy", True),
    ("military", "Quân sự (军事历史)", "jsls", False),
    ("fanfic", "Đồng nhân (同人小说)", "tongren", False),
]
for _key, _label, _slug, _enabled in _POWANJUAN_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "powanjuan_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.powanjuan.cc/{_slug}/",
            "enabled": _enabled,
        }
    )

# 85zw.com
_ZW85_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻小说)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (武侠小说)", "wuxia", False),
    ("romance", "Ngôn tình (言情小说)", "yanqing", False),
    ("historical", "Lịch sử (历史小说)", "lishi", False),
    ("game", "Du hí/Game (网游小说)", "wangyou", False),
    ("scifi", "Khoa huyễn (科幻小说)", "kehuan", False),
]
for _key, _label, _slug, _enabled in _ZW85_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "zw85_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.85zw.com/{_slug}/",
            "enabled": _enabled,
        }
    )

# biqvgeu.cc + diandingnnn.cc — /class/{n}_1.html
_CLASS_N_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻魔法)", 1, True),
    ("wuxia", "Võ hiệp/Tu chân (武侠修真)", 2, False),
    ("urban", "Đô thị (都市言情)", 3, False),
    ("military", "Quân sự (历史军事)", 4, False),
    ("game", "Du hí/Game (网游动漫)", 6, False),
    ("scifi", "Khoa huyễn (科幻小说)", 7, False),
    # class 8 (恐怖) hiện trả list rỗng trên PC — vẫn giữ trong catalog, tắt mặc định
    ("horror", "Kinh dị (恐怖灵异)", 8, False),
]
for _source in ("biqvgeu_cc", "diandingnnn_cc"):
    _base = "https://www.biqvgeu.cc" if _source == "biqvgeu_cc" else "https://www.diandingnnn.cc"
    for _key, _label, _id, _enabled in _CLASS_N_CATEGORIES:
        GENRE_SEEDS.append(
            {
                "source_key": _source,
                "genre_key": _key,
                "label": _label,
                "list_url": f"{_base}/class/{_id}_1.html",
                "enabled": _enabled,
            }
        )

# 8tsw.com
_EIGHTS_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻小说)", "xuanhuanxiaoshuo", True),
    ("wuxia", "Võ hiệp/Tu chân (修真小说)", "xiuzhenxiaoshuo", False),
    ("urban", "Đô thị (都市小说)", "dushixiaoshuo", False),
    ("game", "Du hí/Game (网游小说)", "wangyouxiaoshuo", False),
    ("scifi", "Khoa huyễn (科幻小说)", "kehuanxiaoshuo", False),
]
for _key, _label, _slug, _enabled in _EIGHTS_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "eights_tw_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.8tsw.com/{_slug}/",
            "enabled": _enabled,
        }
    )

# bqg2.com /sort/{n}/1/
_BQG2_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", 1, True),
    ("wuxia", "Võ hiệp/Tu chân (武侠)", 2, False),
    ("urban", "Đô thị (都市)", 3, False),
    ("historical", "Lịch sử (历史)", 4, False),
    ("scifi", "Khoa huyễn (科幻)", 5, False),
    ("game", "Du hí/Game (游戏)", 6, False),
    ("female", "Ngôn tình nữ (女生)", 7, False),
    ("other", "Khác (其他)", 9, False),
]
for _key, _label, _id, _enabled in _BQG2_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "bqg2_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.bqg2.com/sort/{_id}/1/",
            "enabled": _enabled,
        }
    )

# bqge.cc /sort/{slug}/1/
_BQGE_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻小说)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (修真小说)", "xiuzhen", False),
    ("urban", "Đô thị (都市小说)", "dushi", False),
    ("historical", "Lịch sử (历史小说)", "lishi", False),
    ("game", "Du hí/Game (网游小说)", "wangyou", False),
    ("scifi", "Khoa huyễn (科幻小说)", "kehuan", False),
]
for _key, _label, _slug, _enabled in _BQGE_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "bqge_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.bqge.cc/sort/{_slug}/1/",
            "enabled": _enabled,
        }
    )

# bxg123.cc (笔仙阁) — thư mục giống powanjuan
_BXG_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", "xhqh", False),
    ("wuxia", "Võ hiệp/Tu chân (武侠修真)", "wxxz", False),
    ("urban", "Đô thị (都市言情)", "dsyq", False),
    ("scifi", "Khoa huyễn (科幻竞技)", "khjj", False),
    ("fanfic", "Đồng nhân (同人小说)", "trxs", True),
]
for _key, _label, _slug, _enabled in _BXG_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "bxg123_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://bxg123.cc/{_slug}/",
            "enabled": _enabled,
        }
    )

# trxs.cc — chủ yếu đồng nhân
GENRE_SEEDS.append(
    {
        "source_key": "trxs_cc",
        "genre_key": "fanfic",
        "label": "Đồng nhân (同人小说)",
        "list_url": "https://www.trxs.cc/tongren/",
        "enabled": True,
    }
)

# qbtr.cc (全本同人) — nav: 同人 / 常规
_QBTR_CATEGORIES = [
    ("fanfic", "Đồng nhân (同人小说)", "tongren", True),
    ("other", "Khác (常规小说)", "changgui", False),
]
for _key, _label, _slug, _enabled in _QBTR_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "qbtr_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.qbtr.cc/{_slug}/",
            "enabled": _enabled,
        }
    )

# faloo.com (飞卢) — bảng xếp hạng thể loại y_N.html (chương free HTML)
_FALOO_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", 1, False),
    ("wuxia", "Võ hiệp/Tu chân (武侠仙侠)", 6, False),
    ("urban", "Đô thị (都市言情)", 4, False),
    ("military", "Quân sự (军事历史)", 3, False),
    ("scifi", "Khoa huyễn (科幻网游)", 2, False),
    ("horror", "Kinh dị (推理灵异)", 5, True),
    ("fanfic", "Đồng nhân (同人小说)", 44, False),
    ("female", "Ngôn tình nữ (女生小说)", 54, False),
    ("other", "Khác (轻小说)", 97, False),
]
for _key, _label, _id, _enabled in _FALOO_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "faloo_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://b.faloo.com/y_{_id}.html",
            "enabled": _enabled,
        }
    )

# piaotia.com (飘天) — booksort1..9
_PIAOTIA_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻魔法)", 1, False),
    ("wuxia", "Võ hiệp/Tu chân (武侠修真)", 2, False),
    ("urban", "Đô thị (都市言情)", 3, False),
    ("military", "Quân sự (历史军事)", 4, False),
    ("game", "Du hí/Game (网游竞技)", 5, False),
    ("scifi", "Khoa huyễn (科幻小说)", 6, False),
    ("horror", "Kinh dị (恐怖灵异)", 7, True),
    ("fanfic", "Đồng nhân (同人漫画)", 8, False),
    ("other", "Khác (其他类型)", 9, False),
]
for _key, _label, _id, _enabled in _PIAOTIA_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "piaotia_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.piaotia.com/booksort{_id}/0/1.html",
            "enabled": _enabled,
        }
    )

# linovelib — wenku/category bị CF; dùng top rank làm cửa vào + URL tay
GENRE_SEEDS.append(
    {
        "source_key": "linovelib_com",
        "genre_key": "other",
        "label": "Khác (月点击榜)",
        "list_url": "https://www.linovelib.com/top/monthvisit/1.html",
        "enabled": True,
    }
)

# 17k.com — all/book category filters (cần cookie challenge)
_N17K_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", "2_21_0_0_0_0_0_0_1", True),
    ("wuxia", "Võ hiệp/Tu chân (仙侠武侠)", "2_24_0_0_0_0_0_0_1", False),
    ("urban", "Đô thị (都市小说)", "2_3_0_0_0_0_0_0_1", False),
    ("military", "Quân sự (历史军事)", "2_22_0_0_0_0_0_0_1", False),
    ("game", "Du hí/Game (游戏竞技)", "2_23_0_0_0_0_0_0_1", False),
    ("scifi", "Khoa huyễn (科幻末世)", "2_14_0_0_0_0_0_0_1", False),
    ("other", "Khác (悬疑推理)", "2_29_0_0_0_0_0_0_1", False),
    ("female", "Ngôn tình nữ (现代言情)", "3_17_0_0_0_0_0_0_1", False),
]
for _key, _label, _slug, _enabled in _N17K_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "n17k_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.17k.com/all/book/{_slug}.html",
            "enabled": _enabled,
        }
    )

# wenku8 — list cần cookie; class=1.. (nav thật). Manual URL vẫn crawl book free.
_WENKU8_CATEGORIES = [
    ("fantasy", "Huyền huyễn (魔法奇幻)", 1, True),
    ("scifi", "Khoa huyễn (科幻)", 2, False),
    ("horror", "Kinh dị (恐怖灵异)", 3, False),
    ("historical", "Lịch sử (历史军事)", 4, False),
    ("game", "Du hí/Game (游戏竞技)", 5, False),
    ("other", "Khác (学园青春)", 6, False),
    ("romance", "Ngôn tình (恋爱)", 7, False),
    ("female", "Ngôn tình nữ (百合)", 8, False),
]
for _key, _label, _id, _enabled in _WENKU8_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "wenku8_net",
            "genre_key": _key,
            "label": _label,
            "list_url": (
                f"https://www.wenku8.net/modules/article/articlelist.php?class={_id}"
            ),
            "enabled": _enabled,
        }
    )

# ciweimao — book_list/{slug}
_CIWEIMAO_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (仙侠)", "xianxia", False),
    ("urban", "Đô thị (都市)", "dushi", False),
    ("game", "Du hí/Game (游戏)", "youxi", False),
    ("scifi", "Khoa huyễn (科幻)", "kehuan", False),
    ("horror", "Kinh dị (灵异)", "lingyi", False),
    ("fanfic", "Đồng nhân (同人)", "tongren", False),
    ("female", "Ngôn tình nữ (女生)", "nvsheng", False),
]
for _key, _label, _slug, _enabled in _CIWEIMAO_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "ciweimao_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.ciweimao.com/book_list/{_slug}",
            "enabled": _enabled,
        }
    )

# qidian — all?chanId= (nam)
# Sửa 17/9/2026: dòng chanId=5 từng gắn genre_key/label SAI ("military"/
# "Quân sự") trong khi nhãn tiếng Trung đi kèm lại là "历史" (History) —
# tự mâu thuẫn ngay trong chính dòng đó. Verify qua 2 nguồn độc lập
# (qidian.com/all/chanId5-subCateId226/ = "外国历史" — Ngoại quốc SỬ) xác
# nhận chanId=5 đúng là History → đổi về "historical"/"Lịch sử" cho khớp
# quy ước genre_key dùng chung với các site khác (mục 7 — không đổi
# chanId=6 "game" vì chưa verify được, để nguyên).
_QIDIAN_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", 21, True),
    ("wuxia", "Võ hiệp/Tu chân (仙侠)", 2, False),
    ("urban", "Đô thị (都市)", 4, False),
    ("historical", "Lịch sử (历史)", 5, False),
    ("game", "Du hí/Game (游戏)", 6, False),
    ("scifi", "Khoa huyễn (科幻)", 7, False),
    ("horror", "Kinh dị (悬疑)", 8, False),
    ("other", "Khác (轻小说)", 15, False),
]
for _key, _label, _chan, _enabled in _QIDIAN_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "qidian_com",
            "genre_key": _key,
            "label": _label,
            "list_url": (
                f"https://www.qidian.com/all?chanId={_chan}&orderId=&page=1"
                f"&style=1&pageSize=20&siteid=1&pubflag=0&hiddenField=0"
            ),
            "enabled": _enabled,
        }
    )


# --- Nguồn Nhật Bản (Narou API api.syosetu.com) ---
# genre= mã chính thức (dev.syosetu.com/man/api/); order=hyoka.
_SYOSETU_RANKS = [
    (
        "fantasy",
        "Huyền huyễn (ハイファンタジー)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=201&order=hyoka",
        True,
    ),
    (
        "romance",
        "Ngôn tình (異世界恋愛)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=101&order=hyoka",
        False,
    ),
    (
        "urban",
        "Đô thị (現実世界)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=102&order=hyoka",
        False,
    ),
    (
        "scifi",
        "Khoa huyễn (宇宙)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=402&order=hyoka",
        False,
    ),
    (
        "horror",
        "Kinh dị (ホラー)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=305&order=hyoka",
        False,
    ),
    (
        "other",
        "Khác (総合評価)",
        "https://api.syosetu.com/novelapi/api/?out=json&lim=20&order=hyoka",
        False,
    ),
]
for _key, _label, _url, _enabled in _SYOSETU_RANKS:
    GENRE_SEEDS.append(
        {
            "source_key": "syosetu_com",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Nhật Bản (kakuyomu.jp ranking) ---
_KAKUYOMU_RANKS = [
    (
        "fantasy",
        "Huyền huyễn (異世界ファンタジー)",
        "https://kakuyomu.jp/rankings/fantasy/weekly?work_variation=long",
        True,
    ),
    (
        "romance",
        "Ngôn tình (恋愛)",
        "https://kakuyomu.jp/rankings/love_story/weekly?work_variation=long",
        False,
    ),
    (
        "other",
        "Khác (総合)",
        "https://kakuyomu.jp/rankings/all/weekly?work_variation=long",
        False,
    ),
]
for _key, _label, _url, _enabled in _KAKUYOMU_RANKS:
    GENRE_SEEDS.append(
        {
            "source_key": "kakuyomu_com",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Nhật Bản (novelba.com ranking) ---
_NOVELBA_RANKS = [
    (
        "fantasy",
        "Huyền huyễn (ファンタジー)",
        "https://novelba.com/indies/ranking?period=weekly&genre=5",
        True,
    ),
    (
        "romance",
        "Ngôn tình (恋愛)",
        "https://novelba.com/indies/ranking?period=weekly&genre=2",
        False,
    ),
    (
        "urban",
        "Đô thị (現代ドラマ)",
        "https://novelba.com/indies/ranking?period=weekly&genre=18",
        False,
    ),
    (
        "scifi",
        "Khoa huyễn (SF)",
        "https://novelba.com/indies/ranking?period=weekly&genre=6",
        False,
    ),
    (
        "horror",
        "Kinh dị (ホラー)",
        "https://novelba.com/indies/ranking?period=weekly&genre=7",
        False,
    ),
    (
        "other",
        "Khác (完結新着)",
        "https://novelba.com/indies/new/completed",
        False,
    ),
]
for _key, _label, _url, _enabled in _NOVELBA_RANKS:
    GENRE_SEEDS.append(
        {
            "source_key": "novelba_com",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Nhật Bản (NOVEL DAYS ranking) ---
_DAYSNEO_RANKS = [
    (
        "fantasy",
        "Huyền huyễn (ファンタジー)",
        "https://novel.daysneo.com/ranking/?genre_id[]=1",
        True,
    ),
    (
        "romance",
        "Ngôn tình (恋愛・ラブコメ)",
        "https://novel.daysneo.com/ranking/?genre_id[]=2",
        False,
    ),
    (
        "urban",
        "Đô thị (現代ドラマ・社会派)",
        "https://novel.daysneo.com/ranking/?genre_id[]=7",
        False,
    ),
    (
        "scifi",
        "Khoa huyễn (SF)",
        "https://novel.daysneo.com/ranking/?genre_id[]=9",
        False,
    ),
    (
        "other",
        "Khác (総合)",
        "https://novel.daysneo.com/ranking/",
        False,
    ),
]
for _key, _label, _url, _enabled in _DAYSNEO_RANKS:
    GENRE_SEEDS.append(
        {
            "source_key": "daysneo_com",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Hàn Quốc (Novelpia search API) ---
_NOVELPIA_LISTS = [
    ("fantasy", "Huyền huyễn (판타지)", "판타지", True),
    ("romance", "Ngôn tình (로맨스)", "로맨스", False),
    ("scifi", "Khoa huyễn (SF)", "SF", False),
    ("horror", "Kinh dị (공포)", "공포", False),
    ("other", "Khác (웹소설)", "웹소설", False),
]
for _key, _label, _q, _enabled in _NOVELPIA_LISTS:
    GENRE_SEEDS.append(
        {
            "source_key": "novelpia_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://novelpia.com/search?search_text={_q}",
            "enabled": _enabled,
        }
    )

# --- Nguồn Việt Nam (truyenfull.live — thường không cần proxy) ---
_TRUYENFULL_CATEGORIES = [
    ("fantasy", "Huyền huyễn (Tiên hiệp)", "tien-hiep", True),
    ("wuxia", "Võ hiệp/Tu chân (Kiếm hiệp)", "kiem-hiep", False),
    ("romance", "Ngôn tình (Ngôn tình)", "ngon-tinh", False),
    ("game", "Du hí/Game (Võng du)", "vong-du", False),
    ("scifi", "Khoa huyễn (Khoa huyễn)", "khoa-huyen", False),
    ("military", "Quân sự (Quân sự)", "quan-su", False),
    ("historical", "Lịch sử (Lịch sử)", "lich-su", False),
    ("fanfic", "Đồng nhân (Đam mỹ)", "dam-my", False),
    ("other", "Khác (Truyện hot)", "truyen-hot", False),
]
for _key, _label, _slug, _enabled in _TRUYENFULL_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "truyenfull_vn",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://truyenfull.live/the-loai/{_slug}/",
            "enabled": _enabled,
        }
    )

# --- VN cần CRAWL_PROXY_VN (exit IP Việt Nam) ---
for _key, _label, _slug, _enabled in _TRUYENFULL_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "truyenfull_today",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://truyenfull.today/the-loai/{_slug}/",
            "enabled": _enabled,
        }
    )
for _key, _label, _slug, _enabled in _TRUYENFULL_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "dtruyen_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://dtruyen.com/the-loai/{_slug}/",
            "enabled": _enabled,
        }
    )
# sstruyen: thể loại qua /the-loai/{slug}/ (cùng slug họ TruyenFull)
for _key, _label, _slug, _enabled in _TRUYENFULL_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "sstruyen_net",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://sstruyen.net/the-loai/{_slug}/",
            "enabled": _enabled,
        }
    )
# DocLN / Hako — danh sách theo tag/genre thật trên site
_DOCLN_CATEGORIES = [
    ("fantasy", "Huyền huyễn (fantasy)", "fantasy", True),
    ("romance", "Ngôn tình (romance)", "romance", False),
    ("scifi", "Khoa huyễn (sci-fi)", "sci-fi", False),
    ("horror", "Kinh dị (horror)", "horror", False),
    ("other", "Khác (danh sách)", "danh-sach", False),
]
for _key, _label, _slug, _enabled in _DOCLN_CATEGORIES:
    if _slug == "danh-sach":
        _url = "https://docln.net/danh-sach"
    else:
        _url = f"https://docln.net/the-loai/{_slug}"
    GENRE_SEEDS.append(
        {
            "source_key": "docln_net",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Đài Loan / Hoa ngữ (esjzone.cc — tag thật trên site) ---
_ESJZONE_CATEGORIES = [
    ("fantasy", "Huyền huyễn (奇幻)", "奇幻", True),
    ("other", "Khác (異世界)", "异世界", False),
    ("romance", "Ngôn tình (戀愛)", "戀愛", False),
    ("scifi", "Khoa huyễn (科幻)", "科幻", False),
    ("misc", "Phân loại khác (輕小說)", "list-01", False),
]
for _key, _label, _slug, _enabled in _ESJZONE_CATEGORIES:
    if _slug.startswith("list-"):
        _url = f"https://www.esjzone.cc/{_slug}/"
    else:
        _url = f"https://www.esjzone.cc/tags/{_slug}/"
    GENRE_SEEDS.append(
        {
            "source_key": "esjzone_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": _url,
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (zhihu.com 盐选 — chủ yếu Thêm URL; cần cookie) ---
GENRE_SEEDS.append(
    {
        "source_key": "zhihu_com",
        "genre_key": "other",
        "label": "Khác (盐选市场)",
        "list_url": "https://www.zhihu.com/market/",
        "enabled": True,
    }
)

# --- Nguồn Đài Loan (ixdzs.tw) ---
_IXDZS_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", "1", True),
    ("wuxia", "Võ hiệp/Tu chân (修真仙俠)", "2", False),
    ("urban", "Đô thị (都市青春)", "3", False),
    ("romance", "Ngôn tình (言情)", "7", False),
    ("fanfic", "Đồng nhân (耽美同人)", "8", False),
    ("historical", "Lịch sử (台言古言)", "9", False),
    ("other", "Khác (其他)", "0", False),
]
for _key, _label, _sort_id, _enabled in _IXDZS_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "ixdzs_tw",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://ixdzs.tw/sort/{_sort_id}/",
            "enabled": _enabled,
        }
    )

# --- Nguồn Đài Loan (ttkan.co 天天看) ---
_TTKAN_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (仙俠)", "xianxia", False),
    ("urban", "Đô thị (都市)", "dushi", False),
    ("romance", "Ngôn tình (言情)", "gudaiyanqing", False),
    ("game", "Du hí/Game (遊戲)", "youxi", False),
    ("scifi", "Khoa huyễn (科幻)", "kehuan", False),
    ("horror", "Kinh dị (靈異)", "lingyi", False),
    ("military", "Quân sự (軍事)", "junshi", False),
    ("historical", "Lịch sử (歷史)", "lishi", False),
    ("other", "Khác (其它)", "qita", False),
]
for _key, _label, _slug, _enabled in _TTKAN_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "ttkan_co",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.ttkan.co/novel/class/{_slug}",
            "enabled": _enabled,
        }
    )

# --- Nguồn Đài Loan / Hoa ngữ (quanben.io) ---
_QUANBEN_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", "xuanhuan", True),
    ("wuxia", "Võ hiệp/Tu chân (仙侠)", "xianxia", False),
    ("urban", "Đô thị (都市)", "dushi", False),
    ("romance", "Ngôn tình (言情)", "yanqing", False),
    ("game", "Du hí/Game (游戏)", "youxi", False),
    ("scifi", "Khoa huyễn (科幻)", "kehuan", False),
    ("horror", "Kinh dị (灵异)", "lingyi", False),
    ("military", "Quân sự (军事)", "junshi", False),
    ("historical", "Lịch sử (历史)", "lishi", False),
    ("fanfic", "Đồng nhân (耽美)", "danmei", False),
    ("other", "Khác (其它)", "qita", False),
]
for _key, _label, _slug, _enabled in _QUANBEN_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "quanben_io",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.quanben.io/c/{_slug}.html",
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (zongheng.com API) ---
# cateFineId thật từ categoryInfo.cateFineList (adapter docstring).
_ZONGHENG_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻奇幻)", "8101", True),
    ("wuxia", "Võ hiệp/Tu chân (武侠仙侠)", "8102", False),
    ("urban", "Đô thị (都市)", "8103", False),
    ("historical", "Lịch sử (历史)", "8104", False),
    ("scifi", "Khoa huyễn (科幻)", "8105", False),
    ("horror", "Kinh dị (奇闻异事)", "8106", False),
    ("other", "Khác (现实题材)", "8109", False),
    ("misc", "Phân loại khác (其他分类)", "-100", False),
]
for _key, _label, _cid, _enabled in _ZONGHENG_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "zongheng_com",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.zongheng.com/categories?cateFineId={_cid}",
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (jjwxc.net bookbase) ---
_JJWXC_CATEGORIES = [
    ("romance", "Ngôn tình (爱情)", "1", True),
    ("wuxia", "Võ hiệp/Tu chân (武侠)", "2", False),
    ("fantasy", "Huyền huyễn (奇幻)", "3", False),
    ("game", "Du hí/Game (游戏)", "5", False),
    ("scifi", "Khoa huyễn (科幻)", "7", False),
    ("horror", "Kinh dị (惊悚)", "9", False),
    ("other", "Khác (轻小说)", "17", False),
]
for _key, _label, _lx, _enabled in _JJWXC_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "jjwxc_net",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.jjwxc.net/bookbase.php?lx={_lx}&page=1",
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (shubaow.net) ---
_SHUBAOW_CATEGORIES = [
    ("romance", "Ngôn tình (言情)", 1, True),
    ("fanfic", "Đồng nhân (耽美)", 2, False),
    ("yuri", "Bách hợp (百合)", 3, False),
    ("other", "Khác (其他)", 4, False),
    ("male", "Nam văn (男频)", 5, False),
]
for _key, _label, _id, _enabled in _SHUBAOW_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "shubaow_net",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.shubaow.net/list/{_id}.html",
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (tadu.com /store) ---
# URL thật từ nav /store/ (genreId + scope đuôi).
_TADU_CATEGORIES = [
    ("fantasy", "Huyền huyễn (东方玄幻)", "99", "909", True),
    ("urban", "Đô thị (现代都市)", "103", "909", False),
    ("other", "Khác (脑洞创意)", "135", "909", False),
    ("historical", "Lịch sử (历史架空)", "108", "909", False),
    ("military", "Quân sự (军事战争)", "113", "909", False),
    ("game", "Du hí/Game (游戏竞技)", "112", "909", False),
    ("wuxia", "Võ hiệp/Tu chân (武侠仙侠)", "109", "909", False),
    ("scifi", "Khoa huyễn (科幻末世)", "111", "909", False),
    ("horror", "Kinh dị (灵异悬疑)", "128", "909", False),
    ("western", "Kỳ ảo Tây (西方奇幻)", "107", "909", False),
    ("short", "Truyện ngắn (短篇小说)", "281", "909", False),
    ("female", "Ngôn tình nữ (女频全部)", "122", "122", False),
]
for _key, _label, _gid, _scope, _enabled in _TADU_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "tadu_com",
            "genre_key": _key,
            "label": _label,
            "list_url": (
                f"https://www.tadu.com/store/{_gid}-a-0-15-a-20-p-1-{_scope}"
            ),
            "enabled": _enabled,
        }
    )

# --- Nguồn Nhật (alphapolis.co.jp) ---
# category_ids thật từ tag nav (Playwright vượt AWS WAF).
_ALPHAPOLIS_CATEGORIES = [
    ("fantasy", "Huyền huyễn (ファンタジー)", "110400", True),
    ("romance", "Ngôn tình (恋愛)", "110500", False),
    ("scifi", "Khoa huyễn (SF)", "110300", False),
    ("horror", "Kinh dị (ホラー)", "110200", False),
    ("mystery", "Trinh thám (ミステリー)", "110100", False),
    ("historical", "Lịch sử (歴史・時代)", "111100", False),
    ("fanfic", "Đồng nhân (BL)", "119000", False),
    ("light_novel", "Light novel (ライト文芸)", "111500", False),
    ("youth", "Thanh xuân (青春)", "110600", False),
    ("other", "Khác (大衆娯楽)", "110800", False),
]
for _key, _label, _cid, _enabled in _ALPHAPOLIS_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "alphapolis_co_jp",
            "genre_key": _key,
            "label": _label,
            "list_url": (
                f"https://www.alphapolis.co.jp/novel/index?category_ids={_cid}"
            ),
            "enabled": _enabled,
        }
    )

# --- Nguồn Hàn (munpia.com novel-free-list) ---
_MUNPIA_CATEGORIES = [
    ("fantasy", "Huyền huyễn (판타지)", "FANTASY", True),
    ("urban_fantasy", "Huyền huyễn hiện đại (현대판타지)", "NEWFANTASY", False),
    ("wuxia", "Võ hiệp/Tu chân (무협)", "HEROISM", False),
    ("historical", "Lịch sử (대체역사)", "HISTORY", False),
    ("romance", "Ngôn tình (로맨스)", "ROMANCE", False),
    ("game", "Du hí/Game (게임)", "GAME", False),
    ("scifi", "Khoa huyễn (SF)", "SCIENCE", False),
    ("military", "Quân sự (전쟁·밀리터리)", "MILIWAR", False),
    ("drama", "Drama (드라마)", "DRAMA", False),
    ("fusion", "Fusion (퓨전)", "FUSION", False),
    ("sports", "Thể thao (스포츠)", "SPORTS", False),
    ("other", "Khác (기타)", "ETC", False),
]
for _key, _label, _gtype, _enabled in _MUNPIA_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "munpia_com",
            "genre_key": _key,
            "label": _label,
            "list_url": (
                "https://www.munpia.com/novel-free-list"
                f"?novelTabType=ALL&genreType={_gtype}"
                "&orderType=RECENT_SERIES&periodType=DAYS_15&page=0"
            ),
            "enabled": _enabled,
        }
    )

# --- Nguồn Trung Quốc (blqiuge.cc) ---
_BLQIUGE_CATEGORIES = [
    ("fantasy", "Huyền huyễn (玄幻)", "xuanhuanxiaoshuo", True),
    ("wuxia", "Võ hiệp/Tu chân (修真)", "xiuzhenxiaoshuo", False),
    ("urban", "Đô thị (都市)", "dushixiaoshuo", False),
    ("historical", "Lịch sử (穿越)", "chuanyuexiaoshuo", False),
    ("game", "Du hí/Game (网游)", "wangyouxiaoshuo", False),
    ("scifi", "Khoa huyễn (科幻)", "kehuanxiaoshuo", False),
    ("other", "Khác (其他)", "qitaxiaoshuo", False),
]
for _key, _label, _slug, _enabled in _BLQIUGE_CATEGORIES:
    GENRE_SEEDS.append(
        {
            "source_key": "blqiuge_cc",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.blqiuge.cc/{_slug}/",
            "enabled": _enabled,
        }
    )

# --- Nguồn Nhật (pixiv.net novels API) ---
_PIXIV_TAGS = [
    ("fantasy", "Huyền huyễn (ファンタジー)", "ファンタジー", True),
    ("romance", "Ngôn tình (恋愛)", "恋愛", False),
    ("scifi", "Khoa huyễn (SF)", "SF", False),
    ("horror", "Kinh dị (ホラー)", "ホラー", False),
    ("mystery", "Trinh thám (ミステリー)", "ミステリー", False),
    ("historical", "Lịch sử (歴史)", "歴史", False),
    ("fanfic", "Đồng nhân (BL)", "BL", False),
    ("other", "Khác (オリジナル)", "オリジナル", False),
]
for _key, _label, _tag, _enabled in _PIXIV_TAGS:
    GENRE_SEEDS.append(
        {
            "source_key": "pixiv_net",
            "genre_key": _key,
            "label": _label,
            "list_url": f"https://www.pixiv.net/tags/{_tag}/novels",
            "enabled": _enabled,
        }
    )


def catalog_genre_keys() -> set[tuple[str, str]]:
    """(source_key, genre_key) đang được phép hiện trên select."""
    return {(s["source_key"], s["genre_key"]) for s in GENRE_SEEDS}


def get_source(source_key: str) -> SourcePort:
    source = SOURCES.get(source_key)
    if not source:
        raise KeyError(f"Không có source_key='{source_key}' trong registry")
    return source
