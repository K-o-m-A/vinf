import csv
import json
import logging
import urllib.parse
import urllib.request
from collections import Counter

from pyspark.sql import functions as F
from pyspark.sql import types as T

from . import matching
from .jobs import name_keys, norm_udf

log = logging.getLogger("sparkjobs")

# Wikidata vlastnost P1952 = Encyclopaedia Metallum band ID; berieme len polozky s clankom na anglickej Wikipedii
SPARQL = """SELECT ?ma ?title WHERE {
  ?item wdt:P1952 ?ma .
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
}"""
SPARQL_URL = "https://query.wikidata.org/sparql"


def fetch_ground_truth(path):
    query = urllib.parse.urlencode({"query": SPARQL})
    req = urllib.request.Request(f"{SPARQL_URL}?{query}",
                                 headers={"Accept": "text/csv", "User-Agent": "vinf-school-project/1.0"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=120) as resp:
        path.write_bytes(resp.read())


def read_ground_truth(spark, path):
    # Niektore hodnoty P1952 nie su cisla (cela URL, meno kapely), tie preskocime.
    with open(path, encoding="utf-8") as f:
        rows = [(int(r["ma"]), r["title"]) for r in csv.DictReader(f) if r["ma"].isdigit()]
    schema = T.StructType([T.StructField("band_id", T.LongType()), T.StructField("gt_title", T.StringType())])
    return spark.createDataFrame(rows, schema)


def evaluate(spark, gt_path, wiki_dir, out_dir, samples=15):
    """Porovna join s parmi MA id -> clanok z Wikidat a roztriedi chybajuce pary podla priciny."""
    if not gt_path.exists():
        fetch_ground_truth(gt_path)
    bands = spark.read.json(str(out_dir / "bands_wiki"))
    pages = spark.read.parquet(str(wiki_dir / "wiki_pages"))
    redirects = spark.read.parquet(str(wiki_dir / "wiki_redirects"))

    # Wikidata ma aktualny titulok, dump moze mat stary: presmerovanie preklopime na ciel.
    gt = (read_ground_truth(spark, gt_path)
          .join(redirects.withColumnRenamed("title", "gt_title"), "gt_title", "left")
          .select("band_id", F.coalesce("target", "gt_title").alias("gt_title")))
    ours = bands.where(F.col("wiki").isNotNull()).select(F.col("id").alias("band_id"),
                                                        F.col("wiki.title").alias("our_title"))
    in_ma = gt.join(bands.select(F.col("id").alias("band_id")), "band_id").cache()
    gt_titles = gt.select(F.col("gt_title").alias("our_title")).distinct()

    # Presnost: nase pary, o ktorych Wikidata nieco vie (kapela alebo clanok je v Wikidatach).
    checked = (ours.join(gt, "band_id", "left")
               .join(gt_titles.withColumn("title_known", F.lit(True)), "our_title", "left")
               .where(F.col("gt_title").isNotNull() | F.col("title_known").isNotNull()))
    correct = checked.where(F.col("our_title") == F.col("gt_title"))
    wrong = checked.where(~F.coalesce(F.col("our_title") == F.col("gt_title"), F.lit(False)))

    # Chybajuce pary: kapela je v MA aj vo Wikidatach, ale join ju k spravnemu clanku nepripojil.
    missed = in_ma.join(ours, "band_id", "left").where(
        F.col("our_title").isNull() | (F.col("our_title") != F.col("gt_title")))
    keys = name_keys(pages, redirects)
    band_keys = bands.select(F.col("id").alias("band_id"), norm_udf("name").alias("key"))
    page_ids = pages.select(F.col("id").alias("page_id"), F.col("title").alias("gt_title"))
    has_key = (band_keys.join(keys, "key").select("band_id", "page_id")
               .withColumn("same_name", F.lit(True)))
    rows = (missed.join(page_ids, "gt_title", "left").join(has_key, ["band_id", "page_id"], "left")
            .join(bands.drop("wiki").withColumnRenamed("id", "band_id")
                  .select("band_id", F.struct(*[c for c in bands.columns if c not in ("id", "wiki")]).alias("band")),
                  "band_id")
            .join(pages.select(F.col("id").alias("page_id"), F.struct(*pages.columns).alias("page")),
                  "page_id", "left")
            .collect())

    reasons, examples, rejected = Counter(), {}, Counter()
    for r in rows:
        band = r["band"].asDict(recursive=True)
        total, feats = None, None
        if r["page_id"] is None:
            reason = "page_not_parsed"  # clanok nema hudobny infobox, do wiki_pages sa nedostal
        elif not r["same_name"]:
            reason = "name_mismatch"  # ziadny kluc clanku sa nezhoduje s menom kapely
        else:
            total, feats = matching.score(band, r["page"].asDict(recursive=True))
            reason = "lost_to_other_pair" if matching.accept(total, feats) else "rejected_by_score"
            if reason == "rejected_by_score":
                page_members = (r["page"]["members"] or []) + (r["page"]["past_members"] or [])
                rejected[f"score {total}, {'s clenmi' if page_members else 'bez clenov'} v infoboxe"] += 1
        if r["our_title"] is not None:
            reason = "matched_other_page"
        reasons[reason] += 1
        ex = examples.setdefault(reason, [])
        if len(ex) < samples:
            ex.append({"band_id": r["band_id"], "band": band["name"], "country": band.get("country"),
                       "wikidata_title": r["gt_title"], "our_title": r["our_title"], "score": total,
                       "evidence": feats})

    n_correct, n_wrong, n_gt = correct.count(), wrong.count(), in_ma.count()
    stats = {
        "wikidata_pairs": gt.count(),
        "wikidata_pairs_in_ma": n_gt,
        "our_pairs_checked": n_correct + n_wrong,
        "correct": n_correct,
        "wrong": n_wrong,
        "precision": round(n_correct / (n_correct + n_wrong), 3) if n_correct + n_wrong else None,
        "recall": round(n_correct / n_gt, 3) if n_gt else None,
        "missed_by_reason": dict(reasons.most_common()),
        "rejected_by_score": dict(sorted(rejected.items())),
        "wrong_examples": [r.asDict() for r in wrong.limit(samples).collect()],
        "missed_examples": examples,
    }
    (out_dir / "eval_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("eval: presnost %s, uplnost %s (%d spravnych z %d parov z Wikidat)",
             stats["precision"], stats["recall"], n_correct, n_gt)
    return stats
