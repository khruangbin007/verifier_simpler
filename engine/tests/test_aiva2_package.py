"""Tests of aiva2_package: safe unpacking, the R reader, documentation units and stored data."""
import io
import tarfile
import unittest

import helpers
import aiva0_shared as shared
import aiva2_package as package
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
        files, refused = package.unpack_package(path, 10_000_000)
        self.assertEqual(sorted(files), ["pkg/R/a.R"])
        self.assertEqual(len(refused), 4)

    def test_a_member_larger_than_the_cap_is_refused(self):
        path = self.tarball_with([("pkg/R/big.R", tarfile.REGTYPE, b"x" * 5000)])
        files, refused = package.unpack_package(path, 1000)
        self.assertEqual((files, len(refused)), ({}, 1))


class ReadingR(unittest.TestCase):
    def test_snippet_corpus_parses_completely(self):
        for snippet in R_SNIPPETS:
            parts = package.parse_r_source(snippet)
            self.assertFalse([p for p in parts if isinstance(p, tuple)], "not read: %r" % snippet)

    def test_a_broken_expression_is_kept_as_not_read_and_the_rest_is_still_parsed(self):
        units, _ = helpers.units_of({"R/a.R": "good <- function(x) x * 2.5\n\nbad <- function(x) { x +* }\n\nalso_good <- function(y) y / 4.5\n"})
        kinds = [(u["kind"], u["name"]) for u in units if u["file"] == "R/a.R"]
        self.assertIn((shared.KIND_FUNCTION, "good"), kinds)
        self.assertIn((shared.KIND_FUNCTION, "also_good"), kinds)
        self.assertTrue(any(u["kind"] == shared.KIND_NOT_READ for u in units))

    def test_every_non_blank_line_lies_inside_a_unit(self):
        units, result = helpers.units_of(build_samples.f_package(False))
        info = shared.to_plain(result.records["package_info"][0])
        for entry in info["files"]:
            covered = {n for u in units if u["file"] == entry["file"] and u.get("lines") for n in range(u["lines"][0], u["lines"][1] + 1)}
            self.assertFalse(set(entry.get("nonblank_lines", [])) - covered, entry["file"])

    def test_straight_line_functions_are_composed_so_that_a_sign_above_the_return_is_seen(self):
        units, _ = helpers.units_of({"R/a.R": "f <- function(pd, rho, q = 0.999) {\n  a <- qnorm(pd)\n  b <- sqrt(rho) * qnorm(q)\n  pnorm((a - b) / sqrt(1 - rho))\n}\n"})
        function = next(u for u in units if u["kind"] == shared.KIND_FUNCTION)
        text = shared.expr_to_text(shared.expr_from_dict(function["code"]["composed"]))
        self.assertEqual(text, "f = normal_cdf((normal_inverse(pd) - sqrt(rho) * normal_inverse(q)) / sqrt(1 - rho))")
        self.assertEqual([u["name"] for u in units if u["kind"] == shared.KIND_FORMULA], ["a", "b", "f"])

    def test_supporting_code_by_syntax_never_holds_arithmetic_or_a_non_trivial_number(self):
        units, _ = helpers.units_of({"R/a.R": "check <- function(x) {\n  stopifnot(is.numeric(x))\n  invisible(TRUE)\n}\n\n"
                                              "keep <- function(pd, floor = 0.0003) {\n  pd\n}\n\nrate <- function(x) {\n  x * 1.5\n}\n"})
        plumbing = {u["name"]: bool(u["code"]["plumbing"]) for u in units if u["kind"] == shared.KIND_FUNCTION}
        self.assertEqual(plumbing, {"check": True, "keep": False, "rate": False})

    def test_roxygen_blocks_help_pages_tests_and_vignettes_become_units(self):
        units, _ = helpers.units_of(build_samples.f_package(False))
        kinds = {kind: sum(1 for u in units if u["kind"] == kind) for kind in shared.UNIT_KINDS}
        self.assertEqual((kinds[shared.KIND_ROXYGEN], kinds[shared.KIND_HELP], kinds[shared.KIND_TEST], kinds[shared.KIND_VIGNETTE]), (7, 6, 2, 2))
        block = next(u for u in units if u["kind"] == shared.KIND_ROXYGEN and u["name"] == "cond_pd")
        self.assertEqual([t["name"] for t in block["roxygen"]["tags"] if t["tag"] == "param"], ["pd", "rho", "q"])
        self.assertTrue(block["roxygen"]["formulas"][0]["readable"])
        target = next(u for u in units if u["ref"] == block["roxygen"]["documents_ref"])
        self.assertEqual((target["kind"], target["name"], target["code"]["exported"]), (shared.KIND_FUNCTION, "cond_pd", True))
        stale = next(u for u in units if u["kind"] == shared.KIND_HELP and u["name"] == "cond_pd")
        self.assertIs(stale["helppage"]["in_step_with_source"], False)


class StoredData(unittest.TestCase):
    def test_rda_and_rds_are_decoded_without_r_and_profiled(self):
        units, result = helpers.units_of(build_samples.f_package(False))
        tables = {shared.to_plain(t)["object_name"]: shared.to_plain(t) for t in result.records["parameter_tables"]}
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
        function = next(u for u in units if u["kind"] == shared.KIND_FUNCTION and u["name"] == "capital_k")
        self.assertEqual([r["object"] for r in function["code"]["reads_data"]], ["lgd_floors"])

    def test_a_data_file_that_is_not_r_data_is_recorded_as_not_assessed(self):
        units, _ = helpers.units_of({"data/odd.rda": b"this is not R data at all"})
        odd = next(u for u in units if u["file"] == "data/odd.rda")
        self.assertTrue(odd["kind"] == shared.KIND_NOT_READ or not odd["data"]["assessable"])


if __name__ == "__main__":
    unittest.main()
