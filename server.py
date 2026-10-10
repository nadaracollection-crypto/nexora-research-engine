import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify
import trendspyg
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/153.0 Safari/537.36"
}


# ============================================================
# BING AUTOSUGGEST
# ============================================================

def bing_suggest(query):
    try:
        r = requests.get(
            "https://api.bing.com/osjson.aspx",
            params={"query": query},
            headers=HEADERS,
            timeout=5
        )

        if r.status_code != 200:
            return []

        data = r.json()

        if len(data) > 1 and isinstance(data[1], list):
            return data[1]

    except Exception:
        pass

    return []


# ============================================================
# MARKETPLACE QUERY PROFILE
# ============================================================

def marketplace_queries(keyword, marketplace):
    base = keyword.strip()

    profiles = {
        "Shopee": [
            base,
            f"{base} shopee",
            f"{base} murah",
            f"{base} harga shopee",
            f"jual {base} shopee",
            f"{base} terbaru",
            f"{base} terbaik",
            f"{base} original",
            f"{base} promo",
            f"{base} online",
        ],

        "TikTok Shop": [
            base,
            f"{base} tiktok shop",
            f"{base} tiktok",
            f"{base} viral",
            f"{base} fyp",
            f"{base} murah tiktok",
            f"jual {base} tiktok",
            f"{base} review",
            f"{base} rekomendasi",
            f"{base} trending",
        ],

        "Lazada": [
            base,
            f"{base} lazada",
            f"{base} murah lazada",
            f"{base} harga lazada",
            f"jual {base} lazada",
            f"{base} promo lazada",
            f"{base} terbaru",
            f"{base} terbaik",
            f"{base} original",
            f"{base} online",
        ],
    }

    return profiles.get(
        marketplace,
        profiles["Shopee"]
    )


# ============================================================
# KEYWORD ENGINE
# ============================================================

def build_keywords(keyword, marketplace):
    queries = marketplace_queries(
        keyword,
        marketplace
    )

    collected = []

    with ThreadPoolExecutor(
        max_workers=min(10, len(queries))
    ) as executor:

        future_map = {
            executor.submit(
                bing_suggest,
                query
            ): query
            for query in queries
        }

        for future in as_completed(future_map):

            source_query = future_map[future]

            try:
                suggestions = future.result()

                for position, item in enumerate(suggestions):

                    text = str(item).strip()

                    if text:
                        collected.append({
                            "keyword": text,
                            "source": source_query,
                            "position": position,
                        })

            except Exception:
                pass


    # ========================================================
    # MARKETPLACE-SPECIFIC FALLBACK
    # ========================================================

    fallback_by_marketplace = {

        "Shopee": [
            keyword,
            f"{keyword} shopee",
            f"{keyword} murah",
            f"{keyword} terbaru",
            f"{keyword} terbaik",
            f"{keyword} promo",
            f"{keyword} original",
            f"jual {keyword}",
            f"harga {keyword}",
            f"{keyword} online",
        ],

        "TikTok Shop": [
            keyword,
            f"{keyword} tiktok shop",
            f"{keyword} viral",
            f"{keyword} fyp",
            f"{keyword} trending",
            f"{keyword} murah",
            f"{keyword} review",
            f"{keyword} rekomendasi",
            f"jual {keyword}",
            f"{keyword} tiktok",
        ],

        "Lazada": [
            keyword,
            f"{keyword} lazada",
            f"{keyword} murah",
            f"{keyword} promo",
            f"{keyword} terbaru",
            f"{keyword} terbaik",
            f"{keyword} original",
            f"jual {keyword}",
            f"harga {keyword}",
            f"{keyword} online",
        ],
    }

    fallback = fallback_by_marketplace.get(
        marketplace,
        fallback_by_marketplace["Shopee"]
    )

    for item in fallback:

        collected.append({
            "keyword": item,
            "source": "NEXORA FREE fallback",
            "position": 20,
        })


    # ========================================================
    # COUNT SIGNAL
    # ========================================================

    counts = {}
    best_position = {}

    for item in collected:

        text = item["keyword"].strip()
        key = text.lower()

        counts[key] = counts.get(key, 0) + 1

        position = item["position"]

        if key not in best_position:
            best_position[key] = position
        else:
            best_position[key] = min(
                best_position[key],
                position
            )


    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    clean = []
    seen = set()

    for item in collected:

        text = item["keyword"].strip()
        key = text.lower()

        if not text or key in seen:
            continue

        seen.add(key)
        clean.append(text)


    # ========================================================
    # SORT BY REAL SUGGESTION SIGNAL
    # ========================================================

    clean.sort(
        key=lambda x: (
            -counts.get(x.lower(), 0),
            best_position.get(x.lower(), 99),
            len(x),
        )
    )

    return clean[:30], counts, best_position


# ============================================================
# DYNAMIC KEYWORD SIGNAL
# ============================================================

def keyword_signal(
    keyword,
    item,
    counts,
    best_position,
    marketplace
):

    item_key = item.lower()

    occurrence = counts.get(
        item_key,
        1
    )

    position = best_position.get(
        item_key,
        20
    )

    base_words = set(
        keyword.lower().split()
    )

    item_words = set(
        item_key.split()
    )

    overlap = len(
        base_words.intersection(
            item_words
        )
    )


    score = 30

    # Frequency signal
    score += min(
        occurrence * 12,
        36
    )

    # Suggestion position signal
    score += max(
        0,
        24 - (position * 2)
    )

    # Keyword relevance
    score += min(
        overlap * 8,
        24
    )

    # Single appearance penalty
    if occurrence == 1:
        score -= 4


    # ========================================================
    # MARKETPLACE CONTEXT BONUS
    # ========================================================

    lower_item = item_key

    marketplace_words = {

        "Shopee": [
            "shopee",
            "murah",
            "harga",
            "promo",
            "jual",
        ],

        "TikTok Shop": [
            "tiktok",
            "viral",
            "fyp",
            "trending",
            "review",
            "rekomendasi",
        ],

        "Lazada": [
            "lazada",
            "murah",
            "harga",
            "promo",
            "jual",
        ],
    }

    for word in marketplace_words.get(
        marketplace,
        []
    ):

        if word in lower_item:
            score += 3


    return max(
        10,
        min(
            100,
            score
        )
    )


# ============================================================
# SEO ENGINE
# ============================================================

def seo_data(
    keyword,
    marketplace,
    keywords
):

    title = keyword.title()

    alternatives = []

    for item in keywords:

        clean = item.strip()

        if not clean:
            continue

        if clean.lower() == keyword.lower():
            continue

        if clean.lower() not in [
            x.lower()
            for x in alternatives
        ]:

            alternatives.append(
                clean
            )


    # ========================================================
    # MARKETPLACE FALLBACK
    # ========================================================

    fallback_by_marketplace = {

        "Shopee": [
            f"{keyword} murah",
            f"{keyword} terbaru",
            f"{keyword} promo",
            f"jual {keyword}",
            f"harga {keyword}",
        ],

        "TikTok Shop": [
            f"{keyword} viral",
            f"{keyword} fyp",
            f"{keyword} trending",
            f"{keyword} review",
            f"{keyword} rekomendasi",
        ],

        "Lazada": [
            f"{keyword} murah",
            f"{keyword} promo",
            f"{keyword} terbaru",
            f"harga {keyword}",
            f"jual {keyword}",
        ],
    }

    for item in fallback_by_marketplace.get(
        marketplace,
        []
    ):

        if item.lower() not in [
            x.lower()
            for x in alternatives
        ]:

            alternatives.append(
                item
            )


    while len(alternatives) < 3:

        alternatives.append(
            f"{keyword} pilihan"
        )


    a = alternatives[0]
    b = alternatives[1]
    c = alternatives[2]


    # ========================================================
    # MARKETPLACE-SPECIFIC TITLES
    # ========================================================

    if marketplace == "Shopee":

        suggested_titles = [

            f"{a.title()} | Pilihan {title} untuk Kebutuhan Harian",

            f"{b.title()} | Harga Terjangkau & Siap Belanja di Shopee",

            f"{c.title()} | Model Kekinian, Nyaman & Berkualitas",
        ]


    elif marketplace == "TikTok Shop":

        suggested_titles = [

            f"{a.title()} | {title} Viral & Kekinian",

            f"{b.title()} | Rekomendasi {title} untuk TikTok Shop",

            f"{c.title()} | Review, Trend & Pilihan {title}",
        ]


    elif marketplace == "Lazada":

        suggested_titles = [

            f"{a.title()} | Pilihan {title} Terbaru",

            f"{b.title()} | Harga Terjangkau & Promo Lazada",

            f"{c.title()} | Model Kekinian, Nyaman & Berkualitas",
        ]


    else:

        suggested_titles = [

            f"{a.title()} | Pilihan {title} Terbaik",

            f"{b.title()} | Harga Terjangkau",

            f"{c.title()} | Model Kekinian & Berkualitas",
        ]


    # ========================================================
    # DESCRIPTION
    # ========================================================

    description = (
        f"Cari {keyword} dengan pilihan yang "
        f"sesuai kebutuhan. "
        f"Gunakan kata pencarian seperti "
        f"{a}, {b}, dan {c} "
        f"untuk memperluas jangkauan produk "
        f"di {marketplace}. "
        f"Sesuaikan spesifikasi, ukuran, warna, "
        f"bahan, dan keunggulan produk dengan "
        f"barang yang sebenarnya dijual."
    )


    # ========================================================
    # HASHTAGS
    # ========================================================

    hashtag_set = set()


    for word in keyword.split():

        clean = (
            word
            .lower()
            .replace("#", "")
            .replace("-", "")
        )

        if clean:
            hashtag_set.add(
                "#" + clean
            )


    for item in alternatives[:7]:

        tag = (
            item
            .lower()
            .replace(" ", "")
            .replace("#", "")
            .replace("-", "")
        )

        if tag:
            hashtag_set.add(
                "#" + tag
            )


    # Marketplace-specific hashtags

    if marketplace == "Shopee":

        hashtag_set.update([
            "#shopee",
            "#shopeeindonesia",
            "#shopeemurah",
            "#belanjaonline",
        ])

    elif marketplace == "TikTok Shop":

        hashtag_set.update([
            "#tiktokshop",
            "#tiktokshopindonesia",
            "#fyp",
            "#viral",
            "#trending",
        ])

    elif marketplace == "Lazada":

        hashtag_set.update([
            "#lazada",
            "#lazadaindonesia",
            "#lazadamurah",
            "#promo",
        ])


    hashtag_set.add(
        "#produkterbaru"
    )


    return {

        "suggested_titles":
            suggested_titles,

        "description":
            description,

        "hashtags":
            list(hashtag_set)[:15],
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return jsonify({

        "success": True,

        "engine":
            "NEXORA FREE RESEARCH ENGINE",

        "status":
            "online",
    })


# ============================================================
# RESEARCH
# ============================================================

@app.get("/research")
def research():

    keyword = request.args.get(
        "keyword",
        ""
    ).strip()

    marketplace = request.args.get(
        "marketplace",
        "Shopee"
    ).strip()

    region = request.args.get(
        "region",
        "ID"
    ).strip() or "ID"


    if not keyword:

        return jsonify({

            "success": False,

            "message":
                "Keyword wajib diisi.",
        }), 400


    valid_marketplaces = [
        "Shopee",
        "TikTok Shop",
        "Lazada",
    ]

    if marketplace not in valid_marketplaces:

        marketplace = "Shopee"


    started = time.time()


    # ========================================================
    # NEXORA REGIONAL GOOGLE TRENDS
    # ========================================================

    regional_all = []
    regional_selected = []
    regional_error = None

    try:
        regional_env = trendspyg.download_google_trends_explore(
            keyword,
            geo="ID",
            timeframe="today 12-m",
            include_related=False,
            include_geo=True,
            engine="http",
            max_retries=3,
            retry_wait=5,
            cache="disk",
        )

        regional_all = (
            regional_env.get("interest_by_region", [])
            or []
        )

        if region == "ID":
            regional_selected = regional_all
        else:
            regional_selected = [
                item
                for item in regional_all
                if item.get("geo_code") == region
            ]

    except Exception as e:
        regional_error = str(e)


    # ========================================================
    # BUILD MARKETPLACE-SPECIFIC KEYWORDS
    # ========================================================

    keywords, counts, best_position = build_keywords(
        keyword,
        marketplace
    )


    # ========================================================
    # SEO
    # ========================================================

    seo = seo_data(
        keyword,
        marketplace,
        keywords
    )


    # ========================================================
    # SCORE
    # ========================================================

    scored = []

    for item in keywords:

        score = keyword_signal(
            keyword,
            item,
            counts,
            best_position,
            marketplace
        )

        scored.append({

            "keyword":
                item,

            "value":
                score,
        })


    scored.sort(
        key=lambda x:
            x["value"],
        reverse=True
    )


    top = scored[:15]


    top_keys = {
        x["keyword"].lower()
        for x in top
    }


    # ============================================================
    # NEXORA STRICT PRODUCT LONG-TAIL FILTER V2
    # Hanya keyword yang layak menjadi keyword / judul produk.
    # ============================================================

    def is_product_longtail(item, base_keyword):
        text = str(item or "").strip().lower()
        base = str(base_keyword or "").strip().lower()

        if not text or not base:
            return False

        # Keyword harus tetap mengandung produk utama.
        base_tokens = [
            x for x in base.replace("-", " ").split()
            if len(x) >= 2
        ]

        if not base_tokens:
            return False

        if not all(token in text for token in base_tokens):
            return False

        # Query informasional, seller, dan operasional marketplace.
        forbidden = [
            "cara ",
            "bagaimana ",
            "apa itu ",
            "apakah ",
            "kenapa ",
            "mengapa ",
            "kapan ",
            "dimana ",
            "di mana ",
            "tutorial",
            "tips ",
            "strategi ",
            "menghitung",
            "menentukan harga",
            "harga jual",
            "cara jual",
            "cara jualan",
            "cara berjualan",
            "cara menjual",
            "berjualan",
            "jualan",
            "menjual",
            "penjual",
            "penjualan",
            "seller",
            "seller center",
            "toko online",
            "akun seller",
            "daftar seller",
            "menjadi seller",
            "menjadi penjual",
            "modal ",
            "keuntungan ",
            "untung ",
            "omzet",
            "margin",
            "komisi",
            "checkout",
            "pembayaran",
            "transfer",
            "refund",
            "retur",
            "login",
            "password",
            "sandi",
        ]

        if any(word in text for word in forbidden):
            return False

        # Atribut / intent pembeli.
        buyer_terms = [
            "murah",
            "terbaik",
            "premium",
            "original",
            "ori",
            "asli",
            "kekinian",
            "terbaru",
            "viral",
            "fyp",
            "elegan",
            "minimalis",
            "stylish",
            "fashion",
            "fashionable",
            "casual",
            "formal",
            "kulit",
            "kanvas",
            "rajut",
            "import",
            "lokal",
            "wanita",
            "pria",
            "anak",
            "remaja",
            "dewasa",
            "selempang",
            "ransel",
            "tote",
            "sling",
            "shoulder",
            "crossbody",
            "handbag",
            "backpack",
            "travel",
            "kerja",
            "kuliah",
            "sekolah",
            "kantor",
            "kondangan",
            "hadiah",
            "souvenir",
            "diskon",
            "promo",
            "harga",
            "ukuran",
            "besar",
            "kecil",
            "mini",
            "estetik",
            "aesthetic",
        ]

        if text == base:
            return True

        return any(term in text for term in buyer_terms)

    rising = [
        item
        for item in keywords
        if item.lower() not in top_keys
        and is_product_longtail(item, keyword)
    ][:15]


    elapsed = round(
        time.time() - started,
        2
    )


    print(
        f"RESEARCH OK | "
        f"{keyword} | "
        f"{marketplace} | "
        f"{elapsed}s | "
        f"{len(keywords)} keywords"
    )


    return jsonify({

        "success":
            True,

        "keyword":
            keyword,

        "marketplace":
            marketplace,

        "geo":
            region,

        "timeframe":
            "live suggestions",

        "source":
            "Bing Autosuggest + NEXORA FREE ENGINE",

        "indexed_at":
            int(time.time()),

        "data": {

            "interest_over_time":
                [],

            "interest_by_region":
                regional_selected,

            "regional_all":
                regional_all,

            "regional_error":
                regional_error,

            "selected_region":
                region,

            "related_queries": {

                "top":
                    top,

                "rising":
                    rising,
            },

            "keywords":
                keywords,

            "suggested_titles":
                seo["suggested_titles"],

            "description":
                seo["description"],

            "hashtags":
                seo["hashtags"],
        }
    })


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print("")
    print("==========================================")
    print(" NEXORA FREE RESEARCH ENGINE")
    print(" http://127.0.0.1:8765")
    print(" FAST MODE: ON")
    print(" BING REQUESTS: PARALLEL")
    print(" MARKETPLACE ENGINE: ON")
    print(" DYNAMIC KEYWORD SIGNAL: ON")
    print(" SHOPEE / TIKTOK SHOP / LAZADA")
    print("==========================================")
    print("")

    app.run(
        host="0.0.0.0",
        port=8765,
        debug=False,
        threaded=True
    )


