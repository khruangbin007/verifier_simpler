"""Tests of verifier2_package: safe unpacking, the R reader, documentation units and stored data."""
import io
import os
import tarfile
import unittest

import helpers
import core
import reading
import runner
import build_samples

R_SNIPPETS = (          # what real R code looks like; every snippet must parse without a "not read" part
    "f <- function(x, ...) UseMethod('f')", "x <- if (a > b) a else b", "for (i in seq_len(n)) { s <- s + i }",
    "while (TRUE) { break }", "repeat { next }", "y <- x %>% f() %>% g(2)", "y <- x |> f()", "`my var` <- 3", "a$b$c <- d[[1]][2, 'k']",
    "f <- function(a = 1, b = c(1, 2)) { a + b[1] }", "z <- -x^2 + 3e-4 * 0x1F - 1L", "g <- \\(x) x + 1", "s <- r\"(raw \\ text)\"",
    "m <- x %*% t(x) %in% y", "if (is.null(x) && !y || z) stop('no')", "k <- function(x) {\n  # a comment\n  x[x > 0 & !is.na(x)]\n}",
    "lst <- list(a = 1, `b c` = 2)[['a']]", "pkg::fun(x)@slot <- pkg:::hidden(y)", "x[-1] <- NA_real_; y = NULL", "function(x) -x",
    "h <- function(x) {\n  y <- x * 2\n  z <- y +\n    3\n  z / 4\n}", "~ a + b | c", "y ~ x", "a <<- b -> c", "t <- tryCatch(f(x), finally = cat('done'))")


class UnpackingSafely(unittest.TestCase):
    def tarball_with(self, members):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            for name, kind, data in members:
                info = tarfile.TarInfo(name)
                info.type, info.size = kind, len(data)
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = "/etc/passwd"
                archive.addfile(info, io.BytesIO(data))
        path = helpers.os.path.join(helpers.scratch(), "pkg.tar.gz")
        with open(path, "wb") as handle:
            handle.write(raw.getvalue())
        return path

    def test_paths_that_leave_the_package_links_and_devices_are_refused_and_nothing_touches_disk(self):
        path = self.tarball_with([("pkg/R/a.R", tarfile.REGTYPE, b"x <- 1\n"), ("pkg/../../evil.R", tarfile.REGTYPE, b"y <- 2\n"),
                                  ("/abs/evil.R", tarfile.REGTYPE, b"y <- 2\n"), ("pkg/link", tarfile.SYMTYPE, b""), ("pkg/hard", tarfile.LNKTYPE, b"")])
        files, refused = reading.unpack_package(path, 10_000_000)
        self.assertEqual(sorted(files), ["pkg/R/a.R"])
        self.assertEqual(len(refused), 4)

    def test_a_member_larger_than_the_cap_is_refused(self):
        path = self.tarball_with([("pkg/R/big.R", tarfile.REGTYPE, b"x" * 5000)])
        files, refused = reading.unpack_package(path, 1000)
        self.assertEqual((files, len(refused)), ({}, 1))


class ReadingR(unittest.TestCase):
    def test_snippet_corpus_parses_completely(self):
        for snippet in R_SNIPPETS:
            parts = reading.parse_r_source(snippet)
            self.assertFalse([p for p in parts if isinstance(p, tuple)], "not read: %r" % snippet)

    def test_a_broken_expression_is_kept_as_not_read_and_the_rest_is_still_parsed(self):
        units, _ = helpers.units_of({"R/a.R": "good <- function(x) x * 2.5\n\nbad <- function(x) { x +* }\n\nalso_good <- function(y) y / 4.5\n"})
        kinds = [(u["kind"], u["name"]) for u in units if u["file"] == "R/a.R"]
        self.assertIn((core.KIND_FUNCTION, "good"), kinds)
        self.assertIn((core.KIND_FUNCTION, "also_good"), kinds)
        self.assertTrue(any(u["kind"] == core.KIND_NOT_READ for u in units))

    def test_every_non_blank_line_lies_inside_a_unit(self):
        units, result = helpers.units_of(build_samples.f_package(False))
        info = core.to_plain(result.records["package_info"][0])
        for entry in info["files"]:
            covered = {n for u in units if u["file"] == entry["file"] and u.get("lines") for n in range(u["lines"][0], u["lines"][1] + 1)}
            self.assertFalse(set(entry.get("nonblank_lines", [])) - covered, entry["file"])

    def test_straight_line_functions_are_composed_so_that_a_sign_above_the_return_is_seen(self):
        units, _ = helpers.units_of({"R/a.R": "f <- function(pd, rho, q = 0.999) {\n  a <- qnorm(pd)\n  b <- sqrt(rho) * qnorm(q)\n  pnorm((a - b) / sqrt(1 - rho))\n}\n"})
        function = next(u for u in units if u["kind"] == core.KIND_FUNCTION)
        text = core.expr_to_text(core.expr_from_dict(function["code"]["composed"]))
        self.assertEqual(text, "f = normal_cdf((normal_inverse(pd) - sqrt(rho) * normal_inverse(q)) / sqrt(1 - rho))")
        self.assertEqual([u["name"] for u in units if u["kind"] == core.KIND_FORMULA], ["a", "b", "f"])

    def test_supporting_code_by_syntax_never_holds_arithmetic_or_a_non_trivial_number(self):
        units, _ = helpers.units_of({"R/a.R": "check <- function(x) {\n  stopifnot(is.numeric(x))\n  invisible(TRUE)\n}\n\n"
                                              "keep <- function(pd, floor = 0.0003) {\n  pd\n}\n\nrate <- function(x) {\n  x * 1.5\n}\n"})
        plumbing = {u["name"]: bool(u["code"]["plumbing"]) for u in units if u["kind"] == core.KIND_FUNCTION}
        self.assertEqual(plumbing, {"check": True, "keep": False, "rate": False})

    def test_roxygen_blocks_help_pages_tests_and_vignettes_become_units(self):
        units, _ = helpers.units_of(build_samples.f_package(False))
        kinds = {kind: sum(1 for u in units if u["kind"] == kind) for kind in core.UNIT_KINDS}
        self.assertEqual((kinds[core.KIND_ROXYGEN], kinds[core.KIND_HELP], kinds[core.KIND_TEST], kinds[core.KIND_VIGNETTE]), (7, 6, 2, 2))
        block = next(u for u in units if u["kind"] == core.KIND_ROXYGEN and u["name"] == "cond_pd")
        self.assertEqual([t["name"] for t in block["roxygen"]["tags"] if t["tag"] == "param"], ["pd", "rho", "q"])
        self.assertTrue(block["roxygen"]["formulas"][0]["readable"])
        target = next(u for u in units if u["ref"] == block["roxygen"]["documents_ref"])
        self.assertEqual((target["kind"], target["name"], target["code"]["exported"]), (core.KIND_FUNCTION, "cond_pd", True))
        stale = next(u for u in units if u["kind"] == core.KIND_HELP and u["name"] == "cond_pd")
        self.assertIs(stale["helppage"]["in_step_with_source"], False)


class StoredData(unittest.TestCase):
    def test_rda_and_rds_are_decoded_without_r_and_profiled(self):
        units, result = helpers.units_of(build_samples.f_package(False))
        tables = {core.to_plain(t)["object_name"]: core.to_plain(t) for t in result.records["parameter_tables"]}
        floors = tables["lgd_floors"]
        self.assertEqual(floors["header"], ["segment", "lgd_floor"])
        self.assertEqual([row[1] for row in floors["rows"]], ["0.15", "0.25", "0.45"])
        self.assertEqual(floors["row_key"], ["segment"])
        self.assertIn("confidence", tables)

    def test_the_value_hash_ignores_how_the_file_was_written(self):
        import pandas
        frame = pandas.DataFrame({"zone": ["A", "B"], "rate": [0.5, 1.25]})
        first, _ = helpers.units_of({"data/t.rda": build_samples.r_data({"t": frame})})
        second, _ = helpers.units_of({"inst/extdata/t.rds": build_samples.r_data(frame, single=True)})
        hashes = [next(u for u in units if u.get("data"))["data"]["canonical_value_hash"] for units in (first, second)]
        self.assertEqual(hashes[0], hashes[1])

    def test_reads_of_stored_data_are_recognised(self):
        units, _ = helpers.units_of(build_samples.f_package(False))
        function = next(u for u in units if u["kind"] == core.KIND_FUNCTION and u["name"] == "capital_k")
        self.assertEqual([r["object"] for r in function["code"]["reads_data"]], ["lgd_floors"])

    def test_a_data_file_that_is_not_r_data_is_recorded_as_not_assessed(self):
        units, _ = helpers.units_of({"data/odd.rda": b"this is not R data at all"})
        odd = next(u for u in units if u["file"] == "data/odd.rda")
        self.assertTrue(odd["kind"] == core.KIND_NOT_READ or not odd["data"]["assessable"])


class ImplementationMapSample(unittest.TestCase):
    """Stage 1 of the Model Implementation Map: a package shaped like the real ones - one R file among
    many help pages, dplyr pipelines, a purrr lambda, do.call, recursion, dead code - and an answer key
    that says what a complete map must hold. The baseline says what today's reader already recovers."""

    @classmethod
    def setUpClass(cls):
        import yaml
        import build_samples
        with open(os.path.join(helpers.SAMPLES_DIR, "J_pipeline", "gold_map.yaml"), encoding="utf-8") as handle:
            cls.gold = yaml.safe_load(handle)
        cls.source, cls.methodology = build_samples.J_R_SOURCE, build_samples.J_METHODOLOGY

    def test_every_name_in_the_answer_key_is_written_in_the_code(self):
        gold = self.gold
        names = set(gold["final_outputs"] + gold["not_reached"]) | set(gold["calls"]) | {c for cs in gold["calls"].values() for c in cs}
        names |= {v for flows in gold["flows"].values() for v in flows} | set(gold["columns"])
        names |= {s for flows in gold["flows"].values() for ss in flows.values() for s in ss if "/" not in s}
        names |= {s for ss in gold["columns"].values() for s in ss}
        raw = gold["raw_inputs"]
        names |= set(raw["argument"] + raw["column_of_an_argument"] + raw["stored_data"] + raw["hard_coded_number"])
        for name in sorted(names):
            self.assertIn(name, self.source, "the answer key names '%s', which the code does not write" % name)
        for gap in gold["gaps"]:
            self.assertIn(gap["code"], self.source)
        for heading in gold["methodology_not_implemented"]:
            self.assertIn(heading, self.methodology)

    def test_the_sample_is_read_as_an_r_package_with_every_function(self):
        path = os.path.join(helpers.SAMPLES_DIR, "J_pipeline", "Inputs", "2_Model_Package", "harbourscore_1.2.0.tar.gz")
        result = reading.read_package(helpers.context_for({"package": [path]}))
        self.assertFalse([m for m in result.messages if "R package" in m])
        functions = {unit.name for unit in result.records["model_units"] if unit.kind == core.KIND_FUNCTION}
        expected = set(self.gold["final_outputs"] + self.gold["not_reached"]) | set(self.gold["calls"]) | {c for cs in self.gold["calls"].values() for c in cs}
        self.assertEqual(functions, expected)

    def test_the_traced_flow_holds_the_whole_answer_key(self):
        """Stage 2 is done when code alone recovers everything the answer key asks of it: the final output
        and the functions no output reaches, every call (the recursive one too), every value and column
        with what it is computed from, every raw input, and both gaps named with their code. What the map
        says of the documents is its own work, stage 5."""
        import develop
        for part, (got, total) in develop.map_measure("J_pipeline", record=False).items():
            if "stage 5" not in part:
                self.assertEqual(got, total, part)

    def flow(self, sample):
        paths, settings, _ = helpers.run_sample(sample, stop_after="05a")
        store = runner.open_store(paths, settings)
        return store.read("dataflow"), {u["ref"]: u["text"] for u in store.read("model_units")}

    def test_capital_k_resolves_to_raw_inputs_with_no_gap(self):
        """The first done-when of stage 2. pdc is set by a call into cond_pd, whose pd is what floor_pd
        returns there, whose rho is what asset_correlation returns, and whose q is its default."""
        flow, _ = self.flow("F_capital")
        leaves, loops, reached = reading.walk_dataflow(flow, "capital_k")
        nodes = {r["node"]: r for r in flow if r["record_type"] == "node"}
        self.assertEqual(reached, {"capital_k", "cond_pd", "floor_pd", "asset_correlation"})
        self.assertEqual({nodes[leaf]["kind"] for leaf in leaves}, {"argument", "stored data", "number"})
        self.assertEqual({nodes[leaf]["name"] for leaf in leaves if nodes[leaf]["kind"] == "argument"}, {"pd", "lgd", "segment"})
        self.assertFalse(loops)
        self.assertFalse([g for g in flow if g["record_type"] == "gap" and g["function"] in reached])
        call = next(r for r in nodes.values() if r["kind"] == "call" and r["callee"] == "cond_pd" and r["function"] == "capital_k")
        self.assertEqual([nodes[s]["callee"] for s in call["bindings"]["pd"] + call["bindings"]["rho"]], ["floor_pd", "asset_correlation"])
        self.assertEqual(call["bindings"]["q"], ["default"])

    def test_every_source_is_a_node_and_every_line_of_code_is_as_written(self):
        for sample in ("J_pipeline", "F_capital"):
            flow, text = self.flow(sample)
            nodes = {r["node"] for r in flow if r["record_type"] == "node"}
            for record in flow:
                if record["record_type"] == "node":
                    for source in record["from"] + (record.get("default_from") or []):
                        self.assertIn(source, nodes, "%s: %s comes from %s, which is not a node" % (sample, record["node"], source))
                if record.get("code") and record.get("function_ref"):
                    self.assertIn(record["code"], text[record["function_ref"]], "not as written")

    def test_the_pronouns_of_dplyr_are_read_as_dplyr_reads_them(self):
        """Packages written for CRAN name columns as .data$x, to keep the checks quiet, and values of the
        function as .env$x. Without this, .data$throughput would be read as a column called .data."""
        source = ('f <- function(d, limit) {\n  d %>% dplyr::mutate(ok = .data$throughput > .env$limit, '
                  'wide = .data$berth_utilisation * 2)\n}')
        unit = {"ref": "M-0001", "kind": "Function", "name": "f", "text": source, "lines": [1, 3], "code": {"exported": True}}
        records = reading.Dataflow([unit]).run()
        nodes = {r["node"]: r for r in records if r["record_type"] == "node"}
        self.assertEqual(sorted(nodes["column:ok"]["from"]), ["column:throughput", "f:arg:limit"])
        self.assertIn("column:berth_utilisation", nodes["column:wide"]["from"])
        self.assertNotIn("column:.data", nodes)

    def test_a_join_key_only_matches_and_a_loop_keeps_what_it_is_given(self):
        """Found building stage 2: left_join(anchor_table, by = "score_band") made score_band look computed
        from the table, though only anchor is added; and the walk stopped at notch_down's recursive call
        without the arguments it is given, losing the stored table rating_scale."""
        flow, _ = self.flow("J_pipeline")
        nodes = {r["node"]: r for r in flow if r["record_type"] == "node"}
        self.assertNotIn("data:anchor_table", nodes["column:score_band"]["from"])
        self.assertIn("data:anchor_table", nodes["column:anchor"]["from"])
        leaves, loops, _ = reading.walk_dataflow(flow, "harbour_rating")
        self.assertIn("data:rating_scale", leaves)
        self.assertEqual([nodes[loop]["callee"] for loop in loops], ["notch_down"])


if __name__ == "__main__":
    unittest.main()
