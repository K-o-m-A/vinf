import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from extractor.extract import extract_band, extract_discography
from . import matching
from .wiki import norm_name, parse_page, split_title

log = logging.getLogger("sparkjobs")
ROOT = Path(__file__).resolve().parent.parent

STR_LIST = T.ArrayType(T.StringType())
PAGE_SCHEMA = T.StructType([
    T.StructField("id", T.LongType()), T.StructField("title", T.StringType()),
    T.StructField("qualifier", T.StringType()), T.StructField("short_description", T.StringType()),
    T.StructField("name", T.StringType()), T.StructField("background", T.StringType()),
    T.StructField("origin", T.StringType()), T.StructField("years_active", T.StringType()),
    T.StructField("start_year", T.IntegerType()), T.StructField("website", T.StringType()),
    T.StructField("genres", STR_LIST), T.StructField("labels", STR_LIST),
    T.StructField("members", STR_LIST), T.StructField("past_members", STR_LIST),
    T.StructField("associated_acts", STR_LIST), T.StructField("associated_links", STR_LIST),
    T.StructField("spinoffs", STR_LIST), T.StructField("spinoff_of", STR_LIST),
    T.StructField("aliases", STR_LIST), T.StructField("instruments", STR_LIST),
    T.StructField("categories", STR_LIST), T.StructField("length", T.LongType()),
    T.StructField("infobox", T.BooleanType()), T.StructField("lead", T.StringType()),
])
REDIRECT_SCHEMA = T.StructType([T.StructField("title", T.StringType()), T.StructField("target", T.StringType())])
# atributy z Wikipedie, ktore ukladame ku kapele a pocitame ich pokrytie
WIKI_ATTRS = ["lead", "origin", "years_active", "genres", "labels", "members", "past_members", "associated_acts",
              "spinoffs", "spinoff_of", "website", "short_description", "categories"]


def session(app, master):
    # master nastavujeme len ked je zadany, inak by prebil --master zo spark-submit (bez neho local[*])
    builder = SparkSession.builder.appName(app)
    if master:
        builder = builder.master(master)
    spark = (builder
             .config("spark.driver.memory", "6g")
             .config("spark.sql.shuffle.partitions", "64")
             .getOrCreate())
    # balicky projektu pre workery (v klastri nemaju pristup k zdrojakom)
    deps = Path(tempfile.mkdtemp()) / "vinf_deps.zip"
    with zipfile.ZipFile(deps, "w") as z:
        for pkg in ("extractor", "sparkjobs"):
            for f in (ROOT / pkg).glob("*.py"):
                z.write(f, f"{pkg}/{f.name}")
    spark.sparkContext.addPyFile(str(deps))
    spark.sparkContext.setLogLevel("WARN")
    return spark


# ---------------------------------------------------------------- 1. kapely z HTML

def _file_id(path):
    return path.rsplit("/", 1)[1].rsplit(".", 1)[0]


def _band(item):
    path, page = item
    band = extract_band(page)
    if band is None:
        return []
    band["file_id"] = _file_id(path)
    return [(band["file_id"], band)]


def _merge(item):
    _, (band, releases) = item
    band["releases"] = releases or []
    return json.dumps(band, ensure_ascii=False)


def extract_bands(spark, raw_dir, out_dir, partitions):
    """Prvé odovzdanie (extractor/) prepisane do Sparku: kazda stranka sa spracuje na workeri,
    kapela a jej diskografia sa spoja joinom cez id suboru."""
    sc = spark.sparkContext
    bands = sc.wholeTextFiles(f"{raw_dir}/band", minPartitions=partitions).flatMap(_band)
    discs = (sc.wholeTextFiles(f"{raw_dir}/band_disc", minPartitions=partitions)
             .map(lambda kv: (_file_id(kv[0]), extract_discography(kv[1]))))
    shutil.rmtree(out_dir, ignore_errors=True)
    out = bands.leftOuterJoin(discs).map(_merge)
    out.saveAsTextFile(str(out_dir))
    n = spark.read.text(str(out_dir)).count()
    log.info("kapiel: %d -> %s", n, out_dir)


# ---------------------------------------------------------------- 2. wiki dump

def read_pages(spark, dump):
    # Dump citame po elementoch <page>: Hadoop TextInputFormat s oddelovacom "</page>"
    # namiesto konca riadku. bz2 je deliteľný, takze subor sa spracuva paralelne po blokoch.
    conf = {"textinputformat.record.delimiter": "</page>"}
    rdd = spark.sparkContext.newAPIHadoopFile(
        dump, "org.apache.hadoop.mapreduce.lib.input.TextInputFormat",
        "org.apache.hadoop.io.LongWritable", "org.apache.hadoop.io.Text", conf=conf)
    return rdd.map(lambda kv: kv[1])


def parse_wiki(spark, dump, out_dir):
    parsed = read_pages(spark, dump).map(parse_page).filter(lambda p: p is not None).cache()
    pages = parsed.filter(lambda p: p["redirect"] is None)
    redirects = parsed.filter(lambda p: p["redirect"] is not None).map(lambda p: (p["title"], p["redirect"]))
    names = [f.name for f in PAGE_SCHEMA.fields]
    spark.createDataFrame(pages.map(lambda p: tuple(p.get(n) for n in names)), PAGE_SCHEMA) \
        .write.mode("overwrite").parquet(str(out_dir / "wiki_pages"))
    spark.createDataFrame(redirects, REDIRECT_SCHEMA).write.mode("overwrite").parquet(str(out_dir / "wiki_redirects"))
    pages_df = spark.read.parquet(str(out_dir / "wiki_pages"))
    log.info("wiki: %d clankov (%d bez hudobneho infoboxu), %d presmerovani",
             pages_df.count(), pages_df.filter(~F.col("infobox")).count(),
             spark.read.parquet(str(out_dir / "wiki_redirects")).count())


# ---------------------------------------------------------------- 3. join

norm_udf = F.udf(norm_name, T.StringType())
base_title_udf = F.udf(lambda t: split_title(t)[0], T.StringType())


def _score_pairs(rows):
    for row in rows:
        band, page = row["band"].asDict(recursive=True), row["page"].asDict(recursive=True)
        total, feats = matching.score(band, page)
        if matching.accept(total, feats):
            yield (band["id"], page["id"], total, feats["members"], feats["country"], feats["place"],
                   feats["year"], feats["metal"], feats["exact"])


def name_keys(pages, redirects):
    # Mena clanku pre join: titulok bez kvalifikatora ("Death (metal band)" -> "Death"),
    # meno z infoboxu a nazvy presmerovani, ktore na clanok vedu ("Amorphis (band)", "Megadeath").
    return (pages.select("id", base_title_udf("title").alias("alias"))
            .union(pages.select("id", F.col("name").alias("alias")))
            .union(redirects.join(pages.select("id", F.col("title").alias("target")), "target")
                   .select("id", base_title_udf("title").alias("alias")))
            .where(F.col("alias").isNotNull())
            .select(F.col("id").alias("page_id"), norm_udf("alias").alias("key"))
            .where(F.length("key") > 0).distinct())


def join(spark, bands_path, wiki_dir, out_dir):
    bands = spark.read.json(str(bands_path)).withColumn("key", norm_udf("name")).where(F.length("key") > 0)
    pages = spark.read.parquet(str(wiki_dir / "wiki_pages"))
    redirects = spark.read.parquet(str(wiki_dir / "wiki_redirects"))

    keys = name_keys(pages, redirects)

    # Kandidati: equi-join cez normalizovane meno. Kapela "Death" dostane vsetky clanky s klucom "death".
    candidates = (bands.select(F.col("id").alias("band_id"), "key").join(keys, "key")
                  .select("band_id", "page_id").distinct())
    pairs = (candidates
             .join(bands.select(F.col("id").alias("band_id"), F.struct(*bands.columns).alias("band")), "band_id")
             .join(pages.select(F.col("id").alias("page_id"), F.struct(*pages.columns).alias("page")), "page_id"))
    scored = spark.createDataFrame(pairs.rdd.mapPartitions(_score_pairs), T.StructType([
        T.StructField("band_id", T.LongType()), T.StructField("page_id", T.LongType()),
        T.StructField("score", T.IntegerType()), T.StructField("members", T.IntegerType()),
        T.StructField("country", T.BooleanType()), T.StructField("place", T.BooleanType()),
        T.StructField("year", T.BooleanType()), T.StructField("metal", T.BooleanType()),
        T.StructField("exact", T.BooleanType())])).cache()

    # Jeden clanok = jedna kapela a naopak. Prednost ma kapela s menom clanku pred starym menom cez
    # presmerovanie: "Septic Broiler" (MA) ma vyssie skore ako "Dark Tranquillity", lebo years_active na
    # Wikipedii zacina rokom vzniku pod starym menom. Potom vyhra vyssie skore a viac spolocnych clenov.
    order = [F.desc("exact"), F.desc("score"), F.desc("members"), "band_id", "page_id"]
    best = (scored
            .withColumn("rank_page", F.row_number().over(Window.partitionBy("page_id").orderBy(*order)))
            .withColumn("rank_band", F.row_number().over(Window.partitionBy("band_id").orderBy(*order)))
            .where("rank_page = 1 AND rank_band = 1").drop("rank_page", "rank_band").cache())

    wiki_cols = ["id", "title", "length", "infobox", "associated_links"] + WIKI_ATTRS
    wiki = pages.select(F.col("id").alias("page_id"), F.struct(*wiki_cols).alias("wiki"))
    matched = best.join(wiki, "page_id").select(
        "band_id", F.struct("wiki.*", "score", F.struct("members", "country", "place", "year", "metal")
                            .alias("evidence")).alias("wiki"))
    enriched = bands.drop("key").join(matched.withColumnRenamed("band_id", "id"), "id", "left")
    enriched.write.mode("overwrite").json(str(out_dir / "bands_wiki"))

    stats = join_stats(bands, pages, candidates, scored, best, matched)
    (out_dir / "join_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


def join_stats(bands, pages, candidates, scored, best, matched):
    joined = matched.select("wiki.*")
    n = joined.count()
    coverage = {}
    for attr in WIKI_ATTRS:
        col = F.col(attr)
        filled = joined.where(col.isNotNull() & ((F.size(col) > 0) if attr in
                              ("genres", "labels", "members", "past_members", "associated_acts", "spinoffs",
                               "spinoff_of", "categories") else (F.length(col) > 0))).count()
        coverage[attr] = {"pages": filled, "pct": round(100 * filled / n, 1) if n else 0}
    evidence = best.agg(*[F.sum(F.col(c).cast("int")).alias(c) for c in ("country", "place", "year", "metal")],
                        F.sum((F.col("members") > 0).cast("int")).alias("members")).first().asDict()
    return {
        "ma_bands": bands.count(),
        "wiki_music_pages": pages.count(),
        "wiki_pages_without_infobox": pages.where(~F.col("infobox")).count(),
        # background je volitelny (Metallica ho nema), skupinu poznat aj podla clenov
        "wiki_band_pages": pages.where((F.col("background") == "group_or_band") | (
            F.col("background").isNull() & ((F.size("members") > 0) | (F.size("past_members") > 0)))).count(),
        "candidate_pairs": candidates.count(),
        "bands_with_candidate": candidates.select("band_id").distinct().count(),
        "pairs_over_threshold": scored.count(),
        "matched_bands": best.select("band_id").distinct().count(),
        "unique_wiki_pages": best.select("page_id").distinct().count(),
        "evidence": evidence,
        "attribute_coverage": coverage,
        "score_histogram": {str(r["score"]): r["count"] for r in best.groupBy("score").count().orderBy("score").collect()},
    }
